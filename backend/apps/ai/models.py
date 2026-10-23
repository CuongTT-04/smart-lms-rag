
from uuid import uuid4
from django.conf import settings
from django.db import models


class ChatResponseRecord(models.Model):
    """Ownership and feedback for a successfully delivered answer; no prompt storage."""
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.CharField(max_length=7, choices=[('LIKE', 'Thích'), ('DISLIKE', 'Không thích')], null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=models.Q(rating__isnull=True) | models.Q(rating__in=['LIKE', 'DISLIKE']),
            name='ai_chat_valid_rating',
        )]
