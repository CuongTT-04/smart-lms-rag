from unittest.mock import patch
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient
from apps.users.models import User
from common.testing import authenticate_client


class AdminWorkspaceTests(TestCase):
    def test_capabilities_reflect_fresh_permissions_and_deny_non_admins(self):
        user = User.objects.create_user('read_admin', role='ADMIN')
        client = authenticate_client(APIClient(), user)
        user.user_permissions.add(Permission.objects.get(codename='view_user'))
        response = client.get('/api/operations/capabilities/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['capabilities']['accounts'])
        self.assertFalse(response.data['capabilities']['edit_account'])
        user.user_permissions.clear()
        self.assertFalse(client.get('/api/operations/capabilities/').data['capabilities']['accounts'])
        user.role = 'STUDENT'; user.save(update_fields=['role'])
        self.assertEqual(authenticate_client(APIClient(), user).get('/api/operations/capabilities/').status_code, 403)

    @patch('apps.ai.operations.operations_snapshot')
    def test_operations_requires_permission_and_preserves_signal_contract(self, snapshot):
        snapshot.return_value = {'protocol': 'ayo_operations_v1', 'gateway': {'status': 'UNAVAILABLE'}}
        user = User.objects.create_user('ops_admin', role='ADMIN')
        client = authenticate_client(APIClient(), user)
        self.assertEqual(client.get('/api/operations/health/').status_code, 403)
        self.assertEqual(client.get('/api/ai/operations/').status_code, 403)
        snapshot.assert_not_called()
        user.user_permissions.add(Permission.objects.get(codename='view_generationevent'))
        response = client.get('/api/operations/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['ai']['protocol'], 'ayo_operations_v1')
        self.assertIsNone(response.data['ingestion'])
        user.user_permissions.add(Permission.objects.get(codename='view_ingestionjob'))
        self.assertEqual(client.get('/api/operations/health/').data['ingestion']['states'], [])
        from apps.documents.exceptions import DocumentError
        snapshot.side_effect = DocumentError('GENERATION_UNAVAILABLE', 'Unavailable', 503)
        partial = client.get('/api/operations/health/')
        self.assertEqual(partial.status_code, 200)
        self.assertIsNone(partial.data['ai'])
        self.assertEqual(partial.data['ingestion']['states'], [])
        from django.db import DatabaseError
        snapshot.side_effect = DatabaseError('PRIVATE SQL CONNECTION')
        partial = client.get('/api/operations/health/')
        self.assertEqual(partial.status_code, 200)
        self.assertIsNone(partial.data['ai'])
        self.assertNotIn('PRIVATE', str(partial.data))
