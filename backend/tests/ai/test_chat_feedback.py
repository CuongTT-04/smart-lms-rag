from uuid import uuid4
from unittest.mock import patch
from django.db import transaction
from rest_framework.test import APIClient
from tests.documents.test_retrieval_scope import ScopeFixture
from apps.ai.models import ChatResponseRecord


class ChatFeedbackTests(ScopeFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def test_successful_answer_can_be_rated_changed_and_cleared(self):
        with patch('apps.ai.api.views.answer_chat', return_value={
            'status': 'ANSWERED', 'answer': 'Answer [1]', 'citations': [],
        }):
            response = self.client.post('/api/ai/chat/', {
                'course_id': str(self.course.pk), 'question': 'Question?',
            }, format='json')
        self.assertEqual(response.status_code, 200)
        answer_id = response.data['request_id']
        record = ChatResponseRecord.objects.get(pk=answer_id)
        self.assertEqual(record.user_id, self.student.pk)
        url = f'/api/ai/chat/{answer_id}/feedback/'
        for rating in ('LIKE', 'LIKE', 'DISLIKE', None):
            result = self.client.patch(url, {'rating': rating}, format='json')
            self.assertEqual(result.status_code, 200)
            record.refresh_from_db()
            self.assertEqual(record.rating, rating)

    def test_feedback_requires_real_owned_answer_and_valid_rating(self):
        record = ChatResponseRecord.objects.create(user=self.student)
        url = f'/api/ai/chat/{record.pk}/feedback/'
        with transaction.atomic():
            self.assertEqual(self.client.patch(url, {'rating': 'other'}, format='json').status_code, 400)
        with transaction.atomic():
            self.assertEqual(self.client.patch(url, {'rating': 'LIKE', 'user_id': str(self.owner.pk)}, format='json').status_code, 400)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.patch(url, {'rating': 'LIKE'}, format='json').status_code, 404)
        self.assertEqual(self.client.patch(f'/api/ai/chat/{uuid4()}/feedback/', {'rating': 'LIKE'}, format='json').status_code, 404)
        self.client.force_authenticate(None)
        with transaction.atomic():
            self.assertEqual(self.client.patch(url, {'rating': 'LIKE'}, format='json').status_code, 401)
        record.refresh_from_db()
        self.assertIsNone(record.rating)

    def test_failed_generation_does_not_create_rateable_record(self):
        from apps.documents.exceptions import DocumentError
        with patch('apps.ai.api.views.answer_chat', side_effect=DocumentError('GENERATION_UNAVAILABLE', 'Unavailable', 503)):
            response = self.client.post('/api/ai/chat/', {
                'course_id': str(self.course.pk), 'question': 'Question?',
            }, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(ChatResponseRecord.objects.exists())
