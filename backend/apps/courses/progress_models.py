import uuid
from django.db import models


class DocumentCompletion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(
        'courses.Enrollment',
        on_delete=models.CASCADE,
        related_name='document_completions',
    )
    document_version = models.ForeignKey(
        'documents.DocumentVersion',
        on_delete=models.PROTECT,
        related_name='student_completions',
    )
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['completed_at', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['enrollment', 'document_version'],
                name='courses_unique_document_completion',
            ),
        ]
