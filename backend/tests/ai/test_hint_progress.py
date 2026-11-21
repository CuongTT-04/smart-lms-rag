from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.utils import timezone
from rest_framework.test import APIClient
from apps.ai.models import ChatResponseRecord
from apps.courses.assessment_models import Assessment
from tests.documents.test_retrieval_scope import ScopeFixture


class HintProgressTests(ScopeFixture):
    def setUp(self):
        super().setUp()
        self.assessment = Assessment.objects.create(
            session=self.session, title='Ôn tập', description='Mô tả chức năng ALU.',
            kind='TEXT', mode='PRACTICE', is_published=True,
            due_at=timezone.now() + timedelta(days=1))
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.payload = dict(course_id=str(self.course.pk), session_id=str(self.session.pk),
                            assessment_id=str(self.assessment.pk), mode='hint', question='Gợi ý?')
        self.output = dict(status='ANSWERED', mode='hint', answer='Đọc nguồn [1].',
                           citations=[dict(label=1, page_number=1, document_title='CPU')], timing={})

    def send(self, action, previous=None):
        payload = dict(self.payload, hint_action=action)
        if previous:
            payload['previous_hint_id'] = previous
        with patch('apps.ai.api.views.answer_chat', side_effect=lambda **kw: dict(self.output)):
            return self.client.post('/api/ai/chat/', payload, format='json')

    def test_steps_explanation_retry_and_end_are_distinct(self):
        initial = self.send('initial').json()
        explained = self.send('explain_task', initial['request_id']).json()
        self.assertEqual(explained['hint']['step'], 0)
        first = self.send('next_step', explained['request_id']).json()
        retry = self.send('next_step', explained['request_id']).json()
        self.assertEqual(first['answer'], retry['answer'])
        self.assertEqual(first['hint']['step'], 1)
        last = self.send('next_step', first['request_id']).json()
        self.assertFalse(last['hint']['can_advance'])
        self.assertEqual(len({r['answer'] for r in (initial, explained, first, last)}), 4)
        self.assertNotIn('correct_ids', str(last))

    def test_foreign_missing_and_changed_exercise_history_are_rejected(self):
        initial = self.send('initial').json()
        self.assertEqual(self.send('next_step', str(uuid4())).status_code, 404)
        record = ChatResponseRecord.objects.get(pk=initial['request_id'])
        record.user = self.owner
        record.save()
        self.assertEqual(self.send('next_step', initial['request_id']).status_code, 404)
        record.user = self.student
        record.save()
        self.assessment.description = 'Đề đã thay đổi'
        self.assessment.save()
        self.assertEqual(self.send('next_step', initial['request_id']).status_code, 409)

    def test_refusal_has_no_progress_and_next_requires_parent(self):
        self.output.update(status='INSUFFICIENT_EVIDENCE', citations=[])
        result = self.send('initial').json()
        self.assertNotIn('hint', result)
        self.assertIsNone(ChatResponseRecord.objects.get(pk=result['request_id']).hint_state)
        self.assertEqual(self.send('next_step').status_code, 400)
