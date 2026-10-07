import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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
        INVITED = "INVITED", "Invited"
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
                condition=models.Q(status__in=["INVITED", "ACTIVE", "SUSPENDED", "REMOVED"]),
                name="courses_valid_member_status",
            ),
        ]

    def clean(self):
        super().clean()
        if self.role == self.Role.OWNER and self.user_id and self.user.role != "TEACHER":
            raise ValidationError({"user": "The course owner must be a teacher."})

    def __str__(self):
        return f"{self.user} - {self.course} ({self.role})"
