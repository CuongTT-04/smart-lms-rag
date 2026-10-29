
from uuid import uuid4
from django.conf import settings
from django.db import models


class ChatConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE)
    classroom = models.ForeignKey('courses.Classroom', null=True, on_delete=models.CASCADE)
    classroom_session = models.ForeignKey('courses.ClassroomSession', null=True, on_delete=models.CASCADE)
    document = models.ForeignKey('documents.KnowledgeDocument', on_delete=models.CASCADE)
    version = models.ForeignKey('documents.DocumentVersion', on_delete=models.CASCADE)
    title = models.CharField(max_length=80, default='Chat mới')
    next_position = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'document', '-updated_at'], name='ai_conversation_owner_doc')]


class ChatTurn(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    conversation = models.ForeignKey(ChatConversation, related_name='turns', on_delete=models.CASCADE)
    client_message_id = models.UUIDField()
    position = models.PositiveIntegerField()
    question = models.TextField()
    status = models.CharField(max_length=9, choices=[(s, s) for s in ('PENDING', 'COMPLETED', 'FAILED')])
    result = models.JSONField(null=True, blank=True)
    error_code = models.CharField(max_length=48, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    error_status = models.PositiveSmallIntegerField(default=503)
    lease_token = models.UUIDField(null=True)
    lease_expires_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position']
        constraints = [
            models.UniqueConstraint(fields=['conversation', 'client_message_id'], name='ai_turn_client_once'),
            models.UniqueConstraint(fields=['conversation', 'position'], name='ai_turn_position_once'),
            models.UniqueConstraint(fields=['conversation'], condition=models.Q(status='PENDING'), name='ai_turn_one_pending'),
            models.CheckConstraint(condition=models.Q(status__in=['PENDING', 'COMPLETED', 'FAILED']), name='ai_turn_valid_status'),
        ]


class ChatResponseRecord(models.Model):
    """Ownership and feedback for a successfully delivered answer; no prompt storage."""
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    turn = models.OneToOneField(ChatTurn, null=True, blank=True, related_name='feedback', on_delete=models.SET_NULL)
    rating = models.CharField(max_length=7, choices=[('LIKE', 'Thích'), ('DISLIKE', 'Không thích')], null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=models.Q(rating__isnull=True) | models.Q(rating__in=['LIKE', 'DISLIKE']),
            name='ai_chat_valid_rating',
        )]
