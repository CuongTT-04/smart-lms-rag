from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.utils import timezone
from django.db import transaction
from rest_framework.test import APIClient

from apps.ai.models import ChatConversation, ChatTurn, ChatResponseRecord
from apps.documents.exceptions import DocumentError
from tests.documents.test_retrieval_scope import ScopeFixture


class ConversationTests(ScopeFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.selector = dict(course_id=str(self.course.pk), classroom_id=str(self.classroom.pk),
                             session_id=str(self.session.pk), document_id=str(self.doc.pk))

    def create(self):
        response = self.client.post('/api/ai/conversations/', self.selector, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def send(self, conversation_id, question='Câu hỏi đầu', message_id=None):
        return self.client.post('/api/ai/chat/', dict(
            course_id=str(self.course.pk), conversation_id=conversation_id,
            client_message_id=message_id or str(uuid4()), question=question, mode='qa'), format='json')

    def answer(self, **kwargs):
        return dict(request_id=kwargs['request_id'], status='ANSWERED', mode='qa',
                    answer='Nội dung có căn cứ [1]', citations=[dict(label=1, document_id=str(self.doc.pk),
                    version_id=str(self.version.pk), chunk_id='chunk', document_title='PDF',
                    page_number=1, section_title=None, excerpt='Đoạn nguồn')], timing={'total_ms': 1})

    def test_persists_turns_and_loads_history_with_original_feedback(self):
        cid = self.create()
        with patch('apps.ai.conversations.answer_chat', side_effect=self.answer) as generate:
            first = self.send(cid)
            second = self.send(cid, 'Giải thích thêm ý đó')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(generate.call_args.kwargs['history'], [dict(question='Câu hỏi đầu', answer='Nội dung có căn cứ [1]')])
        self.assertEqual(generate.call_args.kwargs['data']['document_ids'], [str(self.doc.pk)])
        answer_id = first.data['request_id']
        self.client.patch(f'/api/ai/chat/{answer_id}/feedback/', {'rating': 'LIKE'}, format='json')
        detail = self.client.get(f'/api/ai/conversations/{cid}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.data['turns']), 2)
        self.assertEqual(detail.data['turns'][0]['result']['request_id'], answer_id)
        self.assertEqual(detail.data['turns'][0]['result']['rating'], 'LIKE')
        listed = self.client.get('/api/ai/conversations/', self.selector)
        self.assertEqual(listed.data['results'][0]['id'], cid)
        self.assertEqual(listed.data['results'][0]['title'], 'Câu hỏi đầu')

    def test_new_conversation_has_independent_context_and_empty_sessions_are_not_listed(self):
        a, b = self.create(), self.create()
        self.assertEqual(self.client.get('/api/ai/conversations/', self.selector).data['results'], [])
        with patch('apps.ai.conversations.answer_chat', side_effect=self.answer) as generate:
            self.send(a)
            self.send(b, 'Phiên mới')
        self.assertEqual(generate.call_args.kwargs['history'], [])
        self.assertEqual(ChatConversation.objects.count(), 2)

    def test_owner_document_version_and_revoked_scope_are_rechecked(self):
        cid = self.create()
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(f'/api/ai/conversations/{cid}/').status_code, 404)
        self.assertEqual(self.send(cid).status_code, 404)
        self.client.force_authenticate(self.student)
        self.enrollment.status = 'WITHDRAWN'; self.enrollment.save()
        self.assertEqual(self.client.get(f'/api/ai/conversations/{cid}/').status_code, 404)
        self.assertEqual(self.send(cid).status_code, 404)

    def test_client_cannot_supply_history_owner_or_another_document(self):
        cid = self.create()
        payload = dict(course_id=str(self.course.pk), conversation_id=cid,
                       client_message_id=str(uuid4()), question='Q', history=[])
        with transaction.atomic():
            self.assertEqual(self.client.post('/api/ai/chat/', payload, format='json').status_code, 400)
        payload.pop('history'); payload['document_ids'] = [str(uuid4())]
        self.assertEqual(self.client.post('/api/ai/chat/', payload, format='json').status_code, 404)
        with transaction.atomic():
            self.assertEqual(self.client.post('/api/ai/conversations/', {**self.selector, 'owner_id': str(self.owner.pk)}, format='json').status_code, 400)

    def test_retry_is_idempotent_and_reused_id_cannot_change_question(self):
        cid, mid = self.create(), str(uuid4())
        with patch('apps.ai.conversations.answer_chat', side_effect=self.answer) as generate:
            first = self.send(cid, message_id=mid)
            retry = self.send(cid, message_id=mid)
            conflict = self.send(cid, 'Đổi câu hỏi', mid)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(retry.data['request_id'], first.data['request_id'])
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(ChatTurn.objects.count(), 1)
        self.assertEqual(conflict.status_code, 409)

    def test_parallel_turn_is_busy_while_same_request_returns_pending(self):
        cid, mid = self.create(), str(uuid4())
        pending = ChatTurn.objects.create(conversation_id=cid, client_message_id=mid, position=1,
            question='Câu hỏi đầu', status='PENDING', lease_token=uuid4(), lease_expires_at=timezone.now()+timedelta(seconds=180))
        with patch('apps.ai.conversations.answer_chat') as generate:
            self.assertEqual(self.send(cid).status_code, 409)
            replay = self.send(cid, message_id=mid)
        self.assertEqual(replay.status_code, 202)
        self.assertEqual(replay.data['turn_id'], str(pending.pk))
        generate.assert_not_called()

    def test_expired_pending_turn_does_not_block_or_enter_memory(self):
        cid = self.create()
        old = ChatTurn.objects.create(conversation_id=cid, client_message_id=uuid4(), position=1,
            question='Lượt treo', status='PENDING', lease_token=uuid4(), lease_expires_at=timezone.now()-timedelta(seconds=1))
        with patch('apps.ai.conversations.answer_chat', side_effect=self.answer) as generate:
            response = self.send(cid)
        old.refresh_from_db()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(old.status, 'FAILED')
        self.assertEqual(generate.call_args.kwargs['history'], [])

    def test_failure_is_stored_but_is_not_rateable_or_used_as_history(self):
        cid = self.create()
        with patch('apps.ai.conversations.answer_chat', side_effect=DocumentError('GENERATION_UNAVAILABLE', 'Unavailable', 503)):
            response = self.send(cid)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(ChatTurn.objects.get().status, 'FAILED')
        self.assertFalse(ChatResponseRecord.objects.exists())
        with patch('apps.ai.conversations.answer_chat', side_effect=self.answer) as generate:
            self.send(cid, 'Thử lại')
        self.assertEqual(generate.call_args.kwargs['history'], [])

    def test_specific_validation_error_survives_history_and_retry(self):
        from apps.ai.rag.errors import public_validation_error
        cid, mid = self.create(), str(uuid4())
        code, message, status = public_validation_error('MISSING_CITATION')
        with patch('apps.ai.conversations.answer_chat', side_effect=DocumentError(code, message, status)) as generate:
            first = self.send(cid, message_id=mid)
            replay = self.send(cid, message_id=mid)
        self.assertEqual(first.data['code'], code)
        self.assertEqual(replay.data['message'], message)
        self.assertEqual(generate.call_count, 1)
        saved = self.client.get(f'/api/ai/conversations/{cid}/').data['turns'][0]
        self.assertEqual(saved['error'], {'code': code, 'message': message})
        self.assertIsNone(saved['result'])

    def test_revocation_during_generation_does_not_save_success(self):
        cid = self.create()
        def revoked(**kwargs):
            self.doc.is_published = False; self.doc.save()
            return self.answer(**kwargs)
        with patch('apps.ai.conversations.answer_chat', side_effect=revoked):
            response = self.send(cid)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ChatTurn.objects.filter(status='COMPLETED').exists())
        self.assertFalse(ChatResponseRecord.objects.exists())

    def test_version_change_hides_old_history_and_feedback(self):
        from apps.documents.models import DocumentVersion
        cid = self.create()
        with patch('apps.ai.conversations.answer_chat', side_effect=self.answer):
            response = self.send(cid)
        self.doc.published_version = DocumentVersion.objects.create(document=self.doc, version_number=2,
            file_name='new.pdf', original_storage_key='new.pdf', file_size_bytes=1,
            checksum_sha256='b'*64, page_count=1, status='EXTRACTED')
        self.doc.save()
        self.assertEqual(self.client.get('/api/ai/conversations/', self.selector).data['results'], [])
        self.assertEqual(self.client.get(f'/api/ai/conversations/{cid}/').status_code, 404)
        self.assertEqual(self.send(cid).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/ai/chat/{response.data['request_id']}/feedback/", {'rating': 'LIKE'}, format='json').status_code, 404)

    def test_active_test_blocks_create_list_detail_send_and_feedback(self):
        from apps.courses.assessment_models import Assessment, AssessmentAttempt
        cid = self.create()
        with patch('apps.ai.conversations.answer_chat', side_effect=self.answer):
            response = self.send(cid)
        assessment = Assessment.objects.create(session=self.session, title='Exam', kind='TEXT', mode='TEST', due_at=timezone.now()+timedelta(hours=1))
        AssessmentAttempt.objects.create(assessment=assessment, student=self.student, request_id=uuid4(), number=1, expires_at=assessment.due_at)
        for result in (self.client.post('/api/ai/conversations/', self.selector, format='json'),
                       self.client.get('/api/ai/conversations/', self.selector),
                       self.client.get(f'/api/ai/conversations/{cid}/'), self.send(cid),
                       self.client.patch(f"/api/ai/chat/{response.data['request_id']}/feedback/", {'rating': 'LIKE'}, format='json')):
            self.assertEqual(result.status_code, 403, result.data)

    def test_late_worker_cannot_complete_an_expired_turn(self):
        cid = self.create()
        def expire(**kwargs):
            ChatTurn.objects.filter(pk=kwargs['request_id']).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
            return self.answer(**kwargs)
        with patch('apps.ai.conversations.answer_chat', side_effect=expire):
            result = self.send(cid)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(ChatTurn.objects.get().status, 'FAILED')
        self.assertFalse(ChatResponseRecord.objects.exists())

    def test_turn_pagination_keeps_order_without_gaps(self):
        cid = self.create()
        ChatTurn.objects.bulk_create([ChatTurn(conversation_id=cid, client_message_id=uuid4(), position=i,
            question=f'Question {i}', status='COMPLETED', result=self.answer(request_id=str(uuid4()))) for i in range(1, 26)])
        latest = self.client.get(f'/api/ai/conversations/{cid}/')
        self.assertEqual([turn['position'] for turn in latest.data['turns']], list(range(6, 26)))
        self.assertEqual(latest.data['next_before'], 6)
        older = self.client.get(f'/api/ai/conversations/{cid}/', {'before': 6})
        self.assertEqual([turn['position'] for turn in older.data['turns']], list(range(1, 6)))
        self.assertIsNone(older.data['next_before'])

    def test_session_pagination_uses_signed_cursor_without_gaps(self):
        sessions = [ChatConversation(user=self.student, course=self.course, classroom=self.classroom,
            classroom_session=self.session, document=self.doc, version=self.version, title=f'Session {i}') for i in range(25)]
        ChatConversation.objects.bulk_create(sessions)
        ChatTurn.objects.bulk_create([ChatTurn(conversation=row, client_message_id=uuid4(), position=1,
            question='Q', status='COMPLETED', result=self.answer(request_id=str(uuid4()))) for row in sessions])
        first = self.client.get('/api/ai/conversations/', self.selector).data
        self.assertEqual(len(first['results']), 20)
        second = self.client.get('/api/ai/conversations/', {**self.selector, 'cursor': first['next_cursor']}).data
        self.assertEqual(len(second['results']), 5)
        self.assertIsNone(second['next_cursor'])
        self.assertEqual(len({r['id'] for r in first['results']+second['results']}), 25)
        invalid = self.client.get('/api/ai/conversations/', {**self.selector, 'cursor': 'tampered'})
        self.assertEqual(invalid.status_code, 400)
