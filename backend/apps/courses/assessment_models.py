import uuid
from django.conf import settings
from django.db import models
from .announcement_storage import announcement_storage


class Assessment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey('courses.ClassroomSession', on_delete=models.PROTECT, related_name='assessments')
    title = models.CharField(max_length=255)
    description = models.TextField(max_length=10000, blank=True, default='')
    kind = models.CharField(max_length=4, choices=[('QUIZ', 'Quiz'), ('TEXT', 'Tự luận/nộp file')])
    mode = models.CharField(max_length=8, choices=[('PRACTICE', 'Ôn tập'), ('TEST', 'Kiểm tra')])
    questions = models.JSONField(default=list)
    hint = models.TextField(max_length=5000, blank=True, default='')
    duration_seconds = models.PositiveIntegerField(default=1800)
    due_at = models.DateTimeField()
    is_published = models.BooleanField(default=False)
    results_published = models.BooleanField(default=False)
    solutions_published = models.BooleanField(default=False)
    removed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class AssessmentAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name='attempts')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=9, default='DRAFT', choices=[('DRAFT', 'Đang làm'), ('SUBMITTED', 'Đã nộp')])
    answers = models.JSONField(default=dict)
    text = models.TextField(max_length=50000, blank=True, default='')
    file = models.FileField(storage=announcement_storage, upload_to='assessment-submissions/', blank=True, default='')
    file_name = models.CharField(max_length=255, blank=True, default='')
    file_type = models.CharField(max_length=30, blank=True, default='')
    revision = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    auto_submitted = models.BooleanField(default=False)
    score = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(max_length=5000, blank=True, default='')
    grade_published = models.BooleanField(default=False)
    moderation_note = models.TextField(max_length=5000, blank=True, default='')

    class Meta:
        ordering = ['-started_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['assessment', 'student', 'request_id'], name='assessment_start_request_unique'),
            models.UniqueConstraint(fields=['assessment', 'student', 'number'], name='assessment_attempt_number_unique'),
            models.UniqueConstraint(fields=['assessment', 'student'], condition=models.Q(status='DRAFT'), name='assessment_one_active_draft'),
            models.CheckConstraint(condition=models.Q(score__isnull=True) | models.Q(score__gte=0, score__lte=10), name='assessment_score_range'),
        ]


class AssessmentEvent(models.Model):
    attempt = models.ForeignKey(AssessmentAttempt, on_delete=models.CASCADE, related_name='events')
    event_id = models.UUIDField()
    kind = models.CharField(max_length=20, choices=[('TAB_HIDDEN', 'Chuyển tab/ẩn trang'), ('FULLSCREEN_EXIT', 'Thoát toàn màn hình')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [models.UniqueConstraint(fields=['attempt', 'event_id'], name='assessment_event_unique')]


class AssessmentGradeAudit(models.Model):
    attempt = models.ForeignKey(AssessmentAttempt, on_delete=models.PROTECT, related_name='grade_history')
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    before = models.JSONField()
    after = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
