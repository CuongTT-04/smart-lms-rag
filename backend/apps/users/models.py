import uuid

from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils import timezone


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
    email_verified_at = models.DateTimeField(null=True, blank=True)
    email_version = models.PositiveIntegerField(default=1, db_default=1)
    auth_version = models.PositiveIntegerField(default=1, db_default=1)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    @property
    def email_verified(self):
        return self.email_verified_at is not None

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
        db_alias = kwargs.get("using") or self._state.db
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            if update_fields & {"status", "is_active"}:
                update_fields.update({"status", "is_active"})
        email_changed = False
        with transaction.atomic(using=db_alias):
            creating = self._state.adding
            if not creating and (
                update_fields is None or update_fields & {"status", "is_active", "role", "email"}
            ):
                previous = (
                    User.objects.using(db_alias)
                    .filter(pk=self.pk)
                    .values("status", "is_active", "role", "email", "auth_version", "email_version")
                    .first()
                )
                if previous is not None:
                    locked_now = (
                        (previous["status"] == self.Status.ACTIVE and self.status != self.Status.ACTIVE)
                        or (previous["is_active"] and not self.is_active)
                    )
                    role_changed = previous["role"] != self.role
                    if (locked_now or role_changed) and self.auth_version <= previous["auth_version"]:
                        self.auth_version = previous["auth_version"] + 1
                        if update_fields is not None:
                            update_fields.add("auth_version")
                    prev_email = (previous["email"] or "").strip().lower()
                    new_email = (self.email or "").strip().lower()
                    if prev_email != new_email:
                        email_changed = True
                        self.email_verified_at = None
                        if self.email_version <= previous["email_version"]:
                            self.email_version = previous["email_version"] + 1
                        if update_fields is not None:
                            update_fields.update({"email_verified_at", "email_version"})
            if update_fields is not None:
                kwargs["update_fields"] = update_fields | {"updated_at"}
            result = super().save(*args, **kwargs)
            if email_changed:
                EmailVerificationToken.objects.using(db_alias).filter(
                    user_id=self.pk, used_at__isnull=True, invalidated_at__isnull=True,
                ).update(invalidated_at=timezone.now())
            if creating:
                if self.role == self.Role.STUDENT:
                    StudentProfile.objects.using(db_alias).get_or_create(user=self)
                elif self.role == self.Role.TEACHER:
                    TeacherProfile.objects.using(db_alias).get_or_create(user=self)
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


class EmailVerificationToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_verification_tokens")
    email = models.EmailField(max_length=254)
    email_version = models.PositiveIntegerField()
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "used_at", "invalidated_at"], name="users_emailver_active_idx"),
        ]

    def __str__(self):
        return f"Email verification token for {self.user_id}"
