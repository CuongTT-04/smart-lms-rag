import json
import secrets
import time
from django.conf import settings
from rest_framework.exceptions import APIException


def redis_client():
    from redis import Redis
    return Redis.from_url(settings.NOTIFICATION_REDIS_URL, socket_connect_timeout=2, socket_timeout=2)


def issue_ticket(user, auth):
    secret = secrets.token_urlsafe(32)
    expiry = int(auth['exp']) if auth else int(time.time()) + 300
    data = json.dumps({'user_id': str(user.pk), 'expires': expiry})
    try:
        redis_client().set(f'notification-ticket:{secret}', data, ex=30)
    except Exception:
        error = APIException('Realtime tạm gián đoạn; bạn vẫn xem được lịch sử thông báo.')
        error.status_code = 503
        raise error
    return {'ticket': secret, 'expires_at': min(int(time.time()) + 30, expiry)}


def consume_ticket(secret):
    if not secret or len(secret) > 100:
        return None
    value = redis_client().getdel(f'notification-ticket:{secret}')
    return json.loads(value) if value else None

