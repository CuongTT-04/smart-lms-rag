import uuid
from django.conf import settings
from django.db import models


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.CharField(max_length=180)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    kind = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    body = models.CharField(max_length=500, blank=True, default='')
    context = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [models.UniqueConstraint(fields=['event_id', 'recipient'], name='notification_event_recipient_unique')]
        indexes = [models.Index(fields=['recipient', '-created_at'], name='notification_inbox_idx'),
                   models.Index(fields=['recipient', 'read_at'], name='notification_unread_idx')]

