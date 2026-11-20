from datetime import timedelta
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.utils import timezone
from rest_framework.test import APIClient
from apps.courses.assessment_models import Assessment, AssessmentAttempt
from apps.ai.policy import enforce_chat_policy
from apps.documents.exceptions import DocumentError
from tests.documents.test_retrieval_scope import ScopeFixture


class ChatPolicyTests(ScopeFixture):
    def values(self, **extra):
        return {'course_id': str(self.course.pk), 'session_id': str(self.session.pk),
                'question': 'Gợi ý?', 'mode': 'qa', **extra}

    def assessment(self, **extra):
        return Assessment.objects.create(session=self.session, title='Quiz', mode='TEST', kind='QUIZ',
            due_at=timezone.now()+timedelta(hours=1), is_published=True,
            questions=[{'id': str(uuid4()), 'prompt': 'Câu hỏi', 'choices': [{'id':'a','text':'A'}],
                        'correct_ids': ['a'], 'hint': 'Secret'}], **extra)

    def attempt(self, assessment, **extra):
        return AssessmentAttempt.objects.create(assessment=assessment, student=self.student,
            request_id=uuid4(), number=1, expires_at=timezone.now()+timedelta(minutes=10), **extra)

    def test_test_blocks_qa_and_hint_then_submission_unblocks(self):
        assessment = self.assessment()
        attempt = self.attempt(assessment)
        for mode in ('qa', 'hint'):
            with self.assertRaises(DocumentError) as caught:
                enforce_chat_policy(self.student, self.values(mode=mode))
            self.assertEqual(caught.exception.code, 'AI_NOT_ALLOWED')
        attempt.status='SUBMITTED'; attempt.save()
        self.assertIsNone(enforce_chat_policy(self.student, self.values()))

    def test_expired_quiz_is_finalized_and_does_not_block(self):
        attempt = self.attempt(self.assessment())
        attempt.expires_at=timezone.now()-timedelta(seconds=1); attempt.save()
        self.assertIsNone(enforce_chat_policy(self.student, self.values()))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'SUBMITTED')

    def test_hint_returns_only_public_question_fields(self):
        assessment = self.assessment(); assessment.mode='PRACTICE'; assessment.save()
        question = assessment.questions[0]
        context = enforce_chat_policy(self.student, self.values(mode='hint',
            assessment_id=str(assessment.pk), question_id=question['id']))
        self.assertEqual(context['question']['prompt'], 'Câu hỏi')
        self.assertNotIn('correct_ids', str(context))
        self.assertNotIn('Secret', str(context))
        self.enrollment.status='WITHDRAWN'; self.enrollment.save()
        with self.assertRaises(DocumentError):
            enforce_chat_policy(self.student, self.values(mode='hint', assessment_id=str(assessment.pk), question_id=question['id']))

    def test_removed_or_unpublished_test_does_not_keep_ai_locked(self):
        assessment = self.assessment()
        attempt = self.attempt(assessment)
        for field, value in [('removed_at', timezone.now()), ('is_published', False)]:
            with self.subTest(field=field):
                setattr(assessment, field, value)
                assessment.save()
                self.assertIsNone(enforce_chat_policy(self.student, self.values()))
                attempt.refresh_from_db()
                self.assertEqual(attempt.status, 'DRAFT')
                setattr(assessment, field, None if field == 'removed_at' else True)

    def test_lost_class_or_course_membership_does_not_lock_other_scopes(self):
        self.attempt(self.assessment())
        for membership, status in [(self.enrollment, 'WITHDRAWN'), (self.member, 'REMOVED')]:
            with self.subTest(membership=membership.__class__.__name__):
                membership.status = status
                membership.save()
                self.assertIsNone(enforce_chat_policy(self.student, self.values()))
                membership.status = 'ACTIVE'
                membership.save()

    def test_draft_or_removed_session_or_class_does_not_keep_ai_locked(self):
        self.attempt(self.assessment())
        for item, field, value in [(self.session, 'is_draft', True),
                (self.session, 'removed_at', timezone.now()), (self.classroom, 'removed_at', timezone.now())]:
            with self.subTest(model=item.__class__.__name__, field=field):
                setattr(item, field, value)
                item.save()
                self.assertIsNone(enforce_chat_policy(self.student, self.values()))
                setattr(item, field, False if field == 'is_draft' else None)
                item.save()

    def test_real_active_test_blocks_all_ai_modes_and_conversations_before_runtime(self):
        self.attempt(self.assessment())
        client = APIClient()
        client.force_authenticate(self.student)
        with patch('apps.ai.services.get_runtime') as qa_runtime, patch('apps.ai.summary.get_runtime') as summary_runtime:
            for mode in ('qa', 'hint', 'summary'):
                payload = self.values(mode=mode, document_ids=[str(self.doc.pk)])
                if mode == 'hint':
                    payload['assessment_id'] = str(uuid4())
                response = client.post('/api/ai/chat/', payload, format='json')
                self.assertEqual((response.status_code, response.data['code']), (403, 'AI_NOT_ALLOWED'))
            response = client.post('/api/ai/conversations/', {
                'course_id': str(self.course.pk), 'document_id': str(self.doc.pk)}, format='json')
            self.assertEqual(response.status_code, 403)
            qa_runtime.assert_not_called()
            summary_runtime.assert_not_called()
        self.assertEqual(client.get('/api/health/').status_code, 200)
        self.assertEqual(client.get(f'/api/courses/{self.course.pk}/').status_code, 200)

    def test_active_test_in_other_course_still_blocks_and_client_cannot_override_it(self):
        self.attempt(self.assessment())
        with self.assertRaises(DocumentError) as caught:
            enforce_chat_policy(self.student, self.values(course_id=str(uuid4())))
        self.assertEqual(caught.exception.code, 'AI_NOT_ALLOWED')
        client = APIClient()
        client.force_authenticate(self.student)
        response = client.post('/api/ai/chat/', self.values(is_test=False, correct_answer='secret'), format='json')
        self.assertEqual(response.status_code, 400)

    def test_hint_model_receives_public_projection_not_answer_key_or_rubric(self):
        from apps.ai.services import answer_chat
        assessment = self.assessment()
        assessment.mode = 'PRACTICE'
        assessment.hint = 'PRIVATE_TEACHER_HINT'
        assessment.questions[0].update(rubric='PRIVATE_RUBRIC', explanation='PRIVATE_EXPLANATION')
        assessment.save()
        output = dict(status='ANSWERED', answer='Đọc định nghĩa trong nguồn [1].',
            references=[dict(label=1, source_id='S1')], usage=None)
        runtime = SimpleNamespace(index=None, embedding=None, catalog={}, config={}, generate=Mock(return_value=output))
        hit = dict(chunk_id='triethoc', text='Triết học nghiên cứu thế giới.', source=dict(
            document_id=str(self.doc.pk), version_id=str(self.version.pk), document_title='Triết học',
            page_number=1, section_title=None))
        with patch('apps.ai.services.retrieve_dense_authorized', return_value=[hit]):
            result = answer_chat(user=self.student, data=self.values(mode='hint',
                assessment_id=str(assessment.pk), question_id=assessment.questions[0]['id']),
                request_id=str(uuid4()), runtime=runtime)
        exercise = runtime.generate.call_args.kwargs['exercise']
        self.assertEqual(set(exercise['question']), {'id', 'prompt', 'choices'})
        for secret in ('correct_ids', 'PRIVATE_TEACHER_HINT', 'PRIVATE_RUBRIC', 'PRIVATE_EXPLANATION', 'Secret'):
            self.assertNotIn(secret, str(runtime.generate.call_args))
            self.assertNotIn(secret, str(result))
