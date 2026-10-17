import json
import time
from unittest.mock import patch, AsyncMock
from django.test import SimpleTestCase, override_settings
from channels.testing import WebsocketCommunicator
from apps.notifications.consumers import NotificationConsumer
from apps.notifications.tickets import issue_ticket, consume_ticket


@override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class SocketTests(SimpleTestCase):
    async def test_valid_ticket_private_group_and_signal(self):
        with patch('apps.notifications.consumers.consume_ticket', return_value={'user_id': 'test-user', 'expires': time.time()+10}), patch.object(NotificationConsumer, 'active', new=AsyncMock(return_value=True)):
            socket = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/?ticket=secret', headers=[(b'origin', b'http://localhost:5173')])
            self.assertTrue((await socket.connect())[0])
            from channels.layers import get_channel_layer
            await get_channel_layer().group_send('notifications.test-user', {'type': 'notifications.changed', 'reason': 'read'})
            message = await socket.receive_json_from()
            self.assertEqual(message, {'type': 'notifications.changed', 'reason': 'read'})
            await socket.disconnect()

    async def test_rejects_origin_and_expired_ticket(self):
        for origin, ticket in [(b'https://attacker.example', {'user_id': 'x', 'expires': time.time()+5}), (b'http://localhost:5173', None), (b'http://localhost:5173', {'user_id': 'x', 'expires': 0})]:
            with patch('apps.notifications.consumers.consume_ticket', return_value=ticket):
                socket = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/?ticket=bad', headers=[(b'origin', origin)])
                self.assertFalse((await socket.connect())[0])
                await socket.disconnect()

    def test_ticket_consumed_atomically_once(self):
        class Store:
            def __init__(self): self.values = {}
            def set(self, key, value, ex):
                self.assert_expiry = ex
                self.values[key] = value
            def getdel(self, key): return self.values.pop(key, None)
        store = Store()
        from types import SimpleNamespace
        with patch('apps.notifications.tickets.redis_client', return_value=store):
            result = issue_ticket(SimpleNamespace(pk='student'), {'exp': int(time.time())+90})
            self.assertEqual(store.assert_expiry, 30)
            self.assertEqual(consume_ticket(result['ticket'])['user_id'], 'student')
            self.assertIsNone(consume_ticket(result['ticket']))

    async def test_socket_expiry_closes_connection(self):
        with patch('apps.notifications.consumers.consume_ticket', return_value={'user_id': 'x', 'expires': time.time()+0.1}), patch.object(NotificationConsumer, 'active', new=AsyncMock(return_value=True)):
            socket = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/?ticket=secret', headers=[(b'origin', b'http://localhost:5173')])
            self.assertTrue((await socket.connect())[0])
            message = await socket.receive_output(timeout=1)
            self.assertEqual(message['code'], 4401)
            await socket.disconnect()
