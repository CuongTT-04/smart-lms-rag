import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import StudentProfile, TeacherProfile, User

REGISTRATION_ROLE_CHOICES = [(User.Role.STUDENT, "Student"), (User.Role.TEACHER, "Teacher")]
logger = logging.getLogger(__name__)


def revoke_refresh_tokens(user):
    for outstanding in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=outstanding)


@transaction.atomic
def update_user_profile(*, actor, changes):
    user = User.objects.select_for_update().get(pk=actor.pk)
    old_avatar_url = user.avatar_url
    if not user.is_active or user.status != User.Status.ACTIVE or user.password != actor.password:
        raise PermissionDenied("Account or authentication changed; sign in again.")
    # Validate against the locked account, including its current role and password.
    from .api.serializers import UserUpdateSerializer
    serializer = UserUpdateSerializer(data=changes, context={"user": user})
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    current_password = values.pop("current_password", None)
    password = values.pop("password", None)
    values.pop("password_confirm", None)
    sensitive = password is not None or ("email" in values and values["email"].lower() != user.email.lower())
    if sensitive and current_password is None:
        raise ValidationError({"current_password": ["Current password is required to change email or password."]})
    if current_password is not None and not user.check_password(current_password):
        raise ValidationError({"current_password": ["Current password is incorrect."]})
    if password is not None:
        try:
            validate_password(password, user=user)
        except ValidationError as error:
            raise ValidationError({"password": error.messages}) from error
    student = values.pop("student_profile", None)
    teacher = values.pop("teacher_profile", None)
    for field, value in values.items():
        setattr(user, field, value)
    updated = set(values)
    if password is not None:
        user.set_password(password)
        updated.add("password")
    user.save(update_fields=updated | {"updated_at"})
    for model, profile_values in ((StudentProfile, student), (TeacherProfile, teacher)):
        if profile_values is not None:
            profile, _ = model.objects.get_or_create(user=user)
            for field, value in profile_values.items():
                setattr(profile, field, value)
            profile.save(update_fields=set(profile_values) | {"updated_at"})
    if password is not None:
        revoke_refresh_tokens(user)
    if "avatar_url" in values and user.avatar_url != old_avatar_url:
        from .avatars import schedule_avatar_cleanup
        schedule_avatar_cleanup(user, old_avatar_url)
    return user, password is not None


def request_password_reset(*, email):
    user = User.objects.filter(email__iexact=email, is_active=True, status=User.Status.ACTIVE).first()
    if user is None or not user.has_usable_password():
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    separator = "&" if "?" in settings.PASSWORD_RESET_URL else "?"
    link = settings.PASSWORD_RESET_URL + separator + urlencode({"uid": uid, "token": token})
    if settings.DEBUG and settings.PASSWORD_RESET_PREVIEW:
        return link
    try:
        send_mail(
            "OHAYO - Reset your password",
            f"Reset your OHAYO password using this link:\n{link}\n\n"
            f"This link expires in {settings.PASSWORD_RESET_TIMEOUT // 60} minutes and can only be used once.\n"
            "If you did not request a password reset, ignore this email.",
            settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False,
        )
    except Exception:
        # Delivery failures must not reveal account existence or reset secrets.
        logger.error("Password reset email delivery failed.")


@transaction.atomic
def confirm_password_reset(*, uid, token, password):
    invalid = ValidationError({"token": ["Reset link is invalid or expired."]})
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.select_for_update().get(pk=user_id)
    except (ValueError, UnicodeDecodeError, ValidationError, User.DoesNotExist) as error:
        raise invalid from error
    if not user.is_active or user.status != User.Status.ACTIVE or not user.has_usable_password():
        raise invalid
    if not default_token_generator.check_token(user, token):
        raise invalid
    try:
        validate_password(password, user=user)
    except ValidationError as error:
        raise ValidationError({"password": error.messages}) from error
    user.set_password(password)
    user.save(update_fields=["password"])
    revoke_refresh_tokens(user)


def authenticate_user(*, username, password):
    user = authenticate(username=username, password=password)
    if user is None or not user.is_active:
        return None
    return user


@transaction.atomic
def register_user(*, username, email, password, full_name, role, avatar_url="", phone="", learning_goal="", bio="", specialization=""):
    if role not in dict(REGISTRATION_ROLE_CHOICES):
        raise ValidationError({"role": "Choose STUDENT or TEACHER."})
    if role == User.Role.STUDENT and (bio or specialization):
        raise ValidationError("Teacher profile fields require the TEACHER role.")
    if role == User.Role.TEACHER and learning_goal:
        raise ValidationError({"learning_goal": "This field requires the STUDENT role."})
    user = User.objects.create_user(
        username=username, email=email, password=password, full_name=full_name,
        avatar_url=avatar_url, phone=phone,
        role=role, status=User.Status.ACTIVE,
        is_staff=False, is_superuser=False,
    )
    if role == User.Role.STUDENT:
        profile = user.student_profile
        profile.learning_goal = learning_goal
        profile.save(update_fields=["learning_goal", "updated_at"])
    else:
        profile = user.teacher_profile
        profile.bio = bio
        profile.specialization = specialization
        profile.save(update_fields=["bio", "specialization", "updated_at"])
    return user
