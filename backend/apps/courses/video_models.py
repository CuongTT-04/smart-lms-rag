import uuid
from django.conf import settings
from django.db import models
from .announcement_storage import announcement_storage


class SessionVideo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey('courses.ClassroomSession', on_delete=models.PROTECT, related_name='videos')
    title = models.CharField(max_length=255)
    description = models.TextField(max_length=5000, blank=True, default='')
    file = models.FileField(storage=announcement_storage, upload_to='videos/')
    content_type = models.CharField(max_length=30)
    duration = models.FloatField()
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at', 'id']


class VideoQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(SessionVideo, on_delete=models.CASCADE, related_name='questions')
    kind = models.CharField(max_length=4, choices=[('MCQ', 'Trắc nghiệm'), ('TEXT', 'Tự luận')])
    prompt = models.TextField(max_length=2000)
    choices = models.JSONField(default=list)
    correct_ids = models.JSONField(default=list)
    multiple = models.BooleanField(default=False)
    hint = models.TextField(max_length=2000, blank=True, default='')
    start_time = models.FloatField()
    rewind_time = models.FloatField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['start_time', 'id']


class VideoProgress(models.Model):
    video = models.ForeignKey(SessionVideo, on_delete=models.CASCADE, related_name='progress_records')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    position = models.FloatField(default=0)
    watched_until = models.FloatField(default=0)
    replay_position = models.FloatField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    playback_credit = models.FloatField(default=1)
    passed = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['video', 'student'], name='unique_video_progress')]


class VideoAnswer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(SessionVideo, on_delete=models.PROTECT, related_name='answers')
    question = models.ForeignKey(VideoQuestion, on_delete=models.PROTECT, related_name='answers')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    question_revision = models.PositiveIntegerField()
    snapshot = models.JSONField()
    selected_ids = models.JSONField(default=list)
    text = models.TextField(max_length=5000, blank=True, default='')
    is_correct = models.BooleanField(null=True)
    rewind_to = models.FloatField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [models.UniqueConstraint(fields=['video', 'student', 'request_id'], name='unique_video_answer_request')]
