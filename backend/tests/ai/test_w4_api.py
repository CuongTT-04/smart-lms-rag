from unittest.mock import patch
from rest_framework.test import APIClient
from apps.documents.exceptions import DocumentError
from tests.documents.test_retrieval_scope import ScopeFixture


class ChatApiTests(ScopeFixture):
    def test_chat_is_not_wrapped_in_request_transaction(self):
        from django.urls import resolve
        self.assertIn('default',resolve('/api/ai/chat/').func._non_atomic_requests)

    def setUp(self):
        super().setUp()
        self.client=APIClient()
        self.data={'question':'Tài liệu?', 'course_id':str(self.course.pk)}

    def test_authentication_error_envelope(self):
        response=self.client.post('/api/ai/chat/',self.data,format='json')
        self.assertEqual(response.status_code,401)
        self.assertEqual(response.data['code'],'UNAUTHENTICATED')
        self.assertIn('request_id',response.data)

    def test_pdf_expected_version_does_not_silently_open_new_version(self):
        from uuid import uuid4
        self.client.force_authenticate(self.student)
        response=self.client.get(f'/api/documents/{self.doc.pk}/view/?expected_version_id={uuid4()}')
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.data['error']['code'],'SCOPE_CHANGED')

    def test_validation_and_unconfigured_runtime(self):
        from django.db import transaction
        self.client.force_authenticate(self.student)
        with transaction.atomic():
            response=self.client.post('/api/ai/chat/',{**self.data,'allowed_version_ids':[]},format='json')
        self.assertEqual(response.status_code,400)
        with patch('apps.ai.services.get_runtime',side_effect=DocumentError('GENERATION_UNAVAILABLE','Chưa cấu hình model.',503)):
            response=self.client.post('/api/ai/chat/',self.data,format='json')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.data['code'],'GENERATION_UNAVAILABLE')

    def test_service_errors_keep_request_id(self):
        self.client.force_authenticate(self.student)
        with patch('apps.ai.api.views.answer_chat',side_effect=DocumentError('SCOPE_CHANGED','Nguồn đã đổi.',409)):
            response=self.client.post('/api/ai/chat/',self.data,format='json')
        self.assertEqual(response.status_code,409)
        self.assertIn('request_id',response.data)
