from django.test import TestCase
from django.db import transaction
from rest_framework.test import APIClient
from apps.users.models import User
from apps.notifications.models import Notification
from apps.notifications.services import notify


class NotificationTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='notice-student', password='test', role='STUDENT')
        self.other = User.objects.create_user(username='notice-other', password='test', role='STUDENT')
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def send(self, key='event-1'):
        return notify(event_id=key, recipients=[self.student.pk, self.other.pk], actor=self.other,
                      kind='TEST', title='Thông báo mới', context={})

    def test_offline_storage_duplicate_and_actor_exclusion(self):
        self.send(); self.send()
        self.assertEqual(Notification.objects.count(), 1)
        response = self.client.get('/api/notifications/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['unread_count'], 1)
        self.assertEqual(response.data['results'][0]['title'], 'Thông báo mới')

    def test_read_state_persists_and_is_private(self):
        self.send()
        item = Notification.objects.get()
        for _ in range(2):
            self.assertEqual(self.client.post(f'/api/notifications/{item.pk}/read/').status_code, 200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(f'/api/notifications/{item.pk}/read/').status_code, 404)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get('/api/notifications/?unread=true').data['count'], 0)

    def test_rollback_does_not_leave_notifications(self):
        try:
            with transaction.atomic():
                self.send()
                raise ValueError('rollback')
        except ValueError:
            pass
        self.assertEqual(Notification.objects.count(), 0)

    def test_read_all_only_own_items(self):
        self.send(); self.send('event-2')
        self.assertEqual(self.client.post('/api/notifications/read-all/').status_code, 200)
        self.send('event-3')
        self.assertEqual(self.client.get('/api/notifications/').data['unread_count'], 1)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/notifications/').status_code, 401)

    def test_redis_failure_after_commit_keeps_database_history(self):
        from unittest.mock import patch
        with patch('channels.layers.get_channel_layer', side_effect=ConnectionError('unavailable')):
            with self.captureOnCommitCallbacks(execute=True):
                self.send()
        self.assertEqual(Notification.objects.filter(recipient=self.student).count(), 1)
