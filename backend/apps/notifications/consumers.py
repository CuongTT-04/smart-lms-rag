import asyncio
import time
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from apps.users.models import User
from .tickets import consume_ticket


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.expiry_task = None
        self.group = None
        origins = [value.decode() for name, value in self.scope['headers'] if name == b'origin']
        if len(origins) != 1 or origins[0] not in settings.CORS_ALLOWED_ORIGINS:
            await self.close(code=4403); return
        try:
            params = parse_qs(self.scope['query_string'].decode())
            ticket = await sync_to_async(consume_ticket)(params.get('ticket', [''])[0])
            if not ticket or ticket['expires'] <= time.time():
                await self.close(code=4401); return
            self.user_id = ticket['user_id']
            if not await self.active():
                await self.close(code=4401); return
            self.group = f'notifications.{self.user_id}'
            await self.channel_layer.group_add(self.group, self.channel_name)
            await self.accept()
            self.expiry_task = asyncio.create_task(self.expire_at(ticket['expires']))
        except Exception:
            await self.close(code=1013)

    @database_sync_to_async
    def active(self):
        return User.objects.filter(pk=self.user_id, is_active=True, status='ACTIVE').exists()

    async def expire_at(self, expiry):
        try:
            while time.time() < expiry:
                await asyncio.sleep(min(30, max(0, expiry - time.time())))
                if time.time() >= expiry or not await self.active():
                    break
                # Restore group membership after a Redis restart; fail closed on outages.
                await self.channel_layer.group_add(self.group, self.channel_name)
            await self.close(code=4401)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.close(code=1013)

    async def disconnect(self, code):
        if self.expiry_task:
            self.expiry_task.cancel()
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def notifications_changed(self, event):
        if not await self.active():
            await self.close(code=4401); return
        await self.send_json(event)

    async def session_close(self, event):
        await self.close(code=4401)

