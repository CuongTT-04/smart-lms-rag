import logging
from asgiref.sync import async_to_sync
from django.db import transaction
from django.utils import timezone
from .models import Notification

logger = logging.getLogger(__name__)


def changed(user_id, reason='created', notification_id=None):
    try:
        from channels.layers import get_channel_layer
        async_to_sync(get_channel_layer().group_send)(f'notifications.{user_id}', {
            'type': 'notifications.changed', 'reason': reason,
            'notification_id': str(notification_id) if notification_id else None,
        })
    except Exception:
        logger.warning('Không thể phát tín hiệu thông báo; lịch sử vẫn được lưu.', exc_info=False)


@transaction.atomic
def notify(*, event_id, recipients, actor=None, kind, title, body='', context=None):
    items = []
    actor_id = getattr(actor, 'pk', actor)
    for user_id in sorted({str(getattr(value, 'pk', value)) for value in recipients if value}, key=str):
        if actor_id and user_id == str(actor_id):
            continue
        item, created = Notification.objects.get_or_create(event_id=str(event_id), recipient_id=user_id,
            defaults={'actor_id': actor_id, 'kind': kind, 'title': title[:255], 'body': body[:500], 'context': context or {}})
        if created:
            items.append(item)
            transaction.on_commit(lambda uid=user_id, nid=item.pk: changed(uid, notification_id=nid))
    return items


def mark_read(user, item=None):
    cutoff = timezone.now()
    query = Notification.objects.filter(recipient=user, read_at__isnull=True, created_at__lte=cutoff)
    if item:
        query = query.filter(pk=item.pk)
    count = query.update(read_at=cutoff)
    if count:
        transaction.on_commit(lambda: changed(user.pk, 'read' if item else 'read_all'))

