import uuid
from hashlib import sha256

from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from .institution_fields import normalize_search, validate_aliases, validate_levels


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
        permissions = [
            ('assign_user_role', 'Can assign application user roles'),
            ('view_platform_overview', 'Can view platform overview'),
        ]
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
                from .teacher_approval import teacher_email_changed
                teacher_email_changed(self, previous_email_version=previous['email_version'], using=db_alias or self._state.db)
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


class Institution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    aliases = models.JSONField(default=list, blank=True, validators=[validate_aliases])
    province = models.CharField(max_length=100)
    campus = models.CharField(max_length=150, blank=True, default='')
    levels = models.JSONField(validators=[validate_levels])
    external_code = models.CharField(max_length=64, blank=True, default='')
    source_url = models.URLField(max_length=500)
    source_checked_at = models.DateField()
    active = models.BooleanField(default=True)
    search_text = models.TextField(editable=False)
    province_key = models.CharField(max_length=150, editable=False)
    identity_key = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name', 'code')

    def prepare_search(self):
        for field in ('name', 'province', 'campus'):
            setattr(self, field, ' '.join(getattr(self, field).split()))
        self.aliases = list(dict.fromkeys(v.strip() for v in self.aliases))
        self.province_key = normalize_search(self.province)
        identity = [normalize_search(self.name), self.province_key, normalize_search(self.campus)]
        self.identity_key = sha256('\x1f'.join(identity).encode()).hexdigest()
        self.search_text = normalize_search(' '.join([self.name, *self.aliases, self.province, self.campus]))

    def save(self, *args, **kwargs):
        self.prepare_search()
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'search_text', 'province_key', 'identity_key', 'aliases'}
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} — {self.campus or self.province}'


class TeacherProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="teacher_profile")
    bio = models.TextField(blank=True, default="")
    specialization = models.CharField(max_length=255, blank=True, default="")
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, null=True, blank=True, related_name='teacher_profiles')
    institution_other_name = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=models.Q(institution__isnull=True) | models.Q(institution_other_name=''),
            name='users_teacher_one_institution_choice',
        )]

    def save(self, *args, **kwargs):
        using = kwargs.get('using') or self._state.db or 'default'
        approval_actor = kwargs.pop('approval_actor', None)
        with transaction.atomic(using=using):
            # Use the same User-first lock order as verification and admin decisions.
            User.objects.using(using).select_for_update().get(pk=self.user_id)
            old = type(self).objects.using(using).filter(pk=self.pk).values(
                'institution_id', 'institution_other_name').first()
            result = super().save(*args, **kwargs)
            from .teacher_approval import ensure_teacher_approval, teacher_affiliation_changed
            ensure_teacher_approval(self, using=using)
            if old is not None:
                teacher_affiliation_changed(self, old, actor=approval_actor, using=using)
            return result

    def __str__(self):
        return f"Teacher profile: {self.user.username}"


class TeacherApproval(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        REVOKED = 'REVOKED', 'Revoked'

    class Source(models.TextChoices):
        AUTO_EDU_VN = 'AUTO_EDU_VN', 'Verified education email'
        ADMIN = 'ADMIN', 'Administrator'
        LEGACY = 'LEGACY', 'Existing teacher migration'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher_profile = models.OneToOneField(TeacherProfile, on_delete=models.CASCADE, related_name='approval')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=12, choices=Source.choices, blank=True, default='')
    reason = models.CharField(max_length=1000, blank=True, default='')
    revision = models.PositiveIntegerField(default=1)
    email_version_at_approval = models.PositiveIntegerField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='teacher_approvals_granted')
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='teacher_approvals_decided')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(revision__gte=1), name='users_teacher_approval_revision_positive'),
            models.CheckConstraint(condition=(
                models.Q(status='PENDING', source='', approved_at__isnull=True,
                         approved_by__isnull=True, email_version_at_approval__isnull=True)
                | models.Q(status='APPROVED', source__in=['AUTO_EDU_VN', 'ADMIN', 'LEGACY'],
                           approved_at__isnull=False, decided_at__isnull=False)
                | models.Q(status__in=['REJECTED', 'REVOKED'], source='ADMIN', decided_at__isnull=False)
            ), name='users_teacher_approval_valid_decision'),
        ]


class TeacherApprovalEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    approval = models.ForeignKey(TeacherApproval, on_delete=models.SET_NULL, null=True, related_name='events')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='teacher_approval_events')
    action = models.CharField(max_length=24)
    reason = models.CharField(max_length=1000)
    revision = models.PositiveIntegerField()
    before = models.JSONField(default=dict)
    after = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at', 'id')
        constraints = [models.UniqueConstraint(fields=['approval', 'revision'], name='users_teacher_approval_event_revision')]


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
