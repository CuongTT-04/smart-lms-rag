import uuid

from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models.functions import Lower


class UserManager(DjangoUserManager):
    def _normalize_status(self, extra_fields):
        extra_fields.setdefault(
            "status",
            User.Status.ACTIVE
            if extra_fields.get("is_active", True)
            else User.Status.INACTIVE,
        )
        active = extra_fields["status"] == User.Status.ACTIVE
        if "is_active" in extra_fields and extra_fields["is_active"] != active:
            raise ValueError("is_active must match the account status.")
        extra_fields["is_active"] = active

    def create_user(self, username, email=None, password=None, **extra_fields):
        self._normalize_status(extra_fields)
        return super().create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("status", User.Status.ACTIVE)
        if extra_fields["role"] != User.Role.ADMIN:
            raise ValueError("Superusers must have the ADMIN role.")
        if extra_fields["status"] != User.Status.ACTIVE:
            raise ValueError("Superusers must have ACTIVE status.")
        self._normalize_status(extra_fields)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        TEACHER = "TEACHER", "Teacher"
        ADMIN = "ADMIN", "Admin"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        BLOCKED = "BLOCKED", "Blocked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=255, blank=True)
    avatar_url = models.URLField(max_length=2048, blank=True, default="", db_default="")
    phone = models.CharField(
        max_length=20, blank=True, default="", db_default="",
        validators=[RegexValidator(r"^\+?[0-9]{8,15}$", "Enter 8-15 digits with an optional leading +.")],
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(Lower("username"), name="users_unique_username_ci"),
            models.UniqueConstraint(
                Lower("email"), condition=~models.Q(email=""), name="users_unique_email_ci",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="ACTIVE", is_active=True)
                    | models.Q(status__in=["INACTIVE", "BLOCKED"], is_active=False)
                ),
                name="users_status_matches_is_active",
            ),
        ]

    def clean(self):
        super().clean()
        self.is_active = self.status == self.Status.ACTIVE

    def save(self, *args, **kwargs):
        # Status is authoritative; Django authentication reads is_active.
        self.is_active = self.status == self.Status.ACTIVE
        update_fields = kwargs.get("update_fields")
        if update_fields:
            update_fields = set(update_fields)
            if update_fields & {"status", "is_active"}:
                update_fields.update({"status", "is_active"})
            kwargs["update_fields"] = update_fields | {"updated_at"}
        with transaction.atomic(using=kwargs.get("using") or self._state.db):
            creating = self._state.adding
            result = super().save(*args, **kwargs)
            if creating:
                if self.role == self.Role.STUDENT:
                    StudentProfile.objects.using(self._state.db).get_or_create(user=self)
                elif self.role == self.Role.TEACHER:
                    TeacherProfile.objects.using(self._state.db).get_or_create(user=self)
            return result

    def get_full_name(self):
        return self.full_name or super().get_full_name()


class StudentProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    learning_goal = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Student profile: {self.user.username}"


class TeacherProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="teacher_profile")
    bio = models.TextField(blank=True, default="")
    specialization = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Teacher profile: {self.user.username}"
