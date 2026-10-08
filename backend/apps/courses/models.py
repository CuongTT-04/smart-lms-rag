import secrets
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def generate_class_code():
    return secrets.token_hex(6).upper()


class Course(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["DRAFT", "PUBLISHED", "ARCHIVED"]),
                name="courses_valid_status",
            ),
        ]

    def clean(self):
        super().clean()
        self.title = (self.title or "").strip()
        if not self.title:
            raise ValidationError({"title": "Course title cannot be empty."})

    def __str__(self):
        return self.title


class CourseMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        TEACHER = "TEACHER", "Teacher"
        ASSISTANT = "ASSISTANT", "Assistant"
        STUDENT = "STUDENT", "Student"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        REMOVED = "REMOVED", "Removed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="course_memberships",
    )
    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.STUDENT
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    joined_at = models.DateTimeField(default=timezone.now)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "user"], name="courses_unique_member"
            ),
            models.UniqueConstraint(
                fields=["course"], condition=models.Q(role="OWNER"),
                name="courses_single_owner",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=["OWNER", "STUDENT"]) | models.Q(status="REMOVED"),
                name="courses_no_coteachers",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=["OWNER", "TEACHER", "ASSISTANT", "STUDENT"]),
                name="courses_valid_member_role",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "SUSPENDED", "REMOVED"]),
                name="courses_valid_member_status",
            ),
        ]

    def clean(self):
        super().clean()
        if self.role == self.Role.OWNER and self.user_id and self.user.role != "TEACHER":
            raise ValidationError({"user": "The course owner must be a teacher."})

    def __str__(self):
        return f"{self.user} - {self.course} ({self.role})"


class AccessPolicy(models.Model):
    class AccessType(models.TextChoices):
        FREE = "FREE", "Free"
        PAID = "PAID", "Paid"

    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "Public"
        PRIVATE = "PRIVATE", "Private"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name="access_policy")
    visibility = models.CharField(max_length=7, choices=Visibility.choices, default=Visibility.PRIVATE)
    access_type = models.CharField(max_length=4, choices=AccessType.choices, default=AccessType.FREE)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    require_class_code = models.BooleanField(default=True)
    require_approval = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=(models.Q(access_type="FREE", price=0) | models.Q(access_type="PAID", price__gt=0)),
            name="courses_valid_access_price",
        )]


class Classroom(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="classrooms")
    name = models.CharField(max_length=255)
    class_code = models.CharField(max_length=12, unique=True, default=generate_class_code, editable=False)
    is_join_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]


class Enrollment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="enrollments")
    student = models.ForeignKey("users.StudentProfile", on_delete=models.PROTECT, related_name="enrollments")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    enrolled_at = models.DateTimeField(default=timezone.now)
    progress_percent = models.FloatField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["classroom", "student"], name="courses_unique_class_enrollment"),
            models.CheckConstraint(condition=models.Q(status__in=["ACTIVE", "COMPLETED", "WITHDRAWN"]), name="courses_valid_enrollment_status"),
            models.CheckConstraint(condition=models.Q(progress_percent__gte=0, progress_percent__lte=100), name="courses_valid_progress"),
        ]


class JoinRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELED = "CANCELED", "Canceled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="join_requests")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="join_requests")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    message = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reviewed_join_requests")
    review_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["classroom", "student"], condition=models.Q(status="PENDING"), name="courses_one_pending_join_request"),
            models.CheckConstraint(condition=models.Q(status__in=["PENDING", "APPROVED", "REJECTED", "CANCELED"]), name="courses_valid_join_status"),
            models.CheckConstraint(condition=(models.Q(status__in=["PENDING", "CANCELED"], reviewed_by__isnull=True, reviewed_at__isnull=True) | models.Q(status__in=["APPROVED", "REJECTED"], reviewed_by__isnull=False, reviewed_at__isnull=False)), name="courses_valid_join_review"),
        ]
