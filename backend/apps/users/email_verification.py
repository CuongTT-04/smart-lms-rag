"""Email verification workflow and transactional post-verification hook for W9-ADM-01/02."""
from datetime import timedelta
from hashlib import sha256
import logging
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import EmailVerificationToken, User
from .rate_limit import check_and_increment, check_and_set_cooldown

logger = logging.getLogger(__name__)
_email_verified_hooks = []


class EmailVerificationRateLimited(Exception):
    def __init__(self, detail, retry_after):
        super().__init__(detail)
        self.detail = detail
        self.retry_after = max(1, int(retry_after))


def register_email_verified_hook(handler):
    """Register a callable invoked inside the confirm transaction: handler(user)."""
    if handler not in _email_verified_hooks:
        _email_verified_hooks.append(handler)
    return handler


def unregister_email_verified_hook(handler):
    if handler in _email_verified_hooks:
        _email_verified_hooks.remove(handler)


def on_email_verified(user):
    """Invoke registered hooks inside the active email-confirmation transaction."""
    handlers = list(_email_verified_hooks)
    for dotted in getattr(settings, "USERS_EMAIL_VERIFIED_HOOKS", ()):
        hook = import_string(dotted)
        if hook not in handlers:
            handlers.append(hook)
    for handler in handlers:
        handler(user)


def hash_verification_token(raw_token):
    return sha256(raw_token.encode("utf-8")).hexdigest()


def build_verification_url(raw_token):
    base = settings.EMAIL_VERIFICATION_URL
    separator = "&" if "?" in base else "?"
    return base + separator + urlencode({"token": raw_token})


def send_email_verification(*, actor):
    """Issue a one-time 24h verification link to the server-stored email of the signed-in user."""
    user = User.objects.get(pk=actor.pk)
    if not user.is_active or user.status != User.Status.ACTIVE:
        raise ValidationError({"detail": ["Account is not active."]})
    email = (user.email or "").strip().lower()
    if not email:
        raise ValidationError({"email": ["Account does not have an email address."]})
    if user.email_verified:
        return {"already_verified": True, "email_verified": True}

    cooldown_seconds = int(getattr(settings, "EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS", 60))
    ok_cooldown, retry_after = check_and_set_cooldown(
        "email_verify_cooldown", str(user.pk), cooldown_seconds=cooldown_seconds,
    )
    if not ok_cooldown:
        raise EmailVerificationRateLimited(
            "Please wait before requesting another verification email.", retry_after,
        )

    max_per_hour = int(getattr(settings, "EMAIL_VERIFICATION_MAX_PER_HOUR", 3))
    ok_hourly, hourly_retry = check_and_increment(
        "email_verify_hourly", str(user.pk), limit=max_per_hour, window_seconds=3600,
    )
    if not ok_hourly:
        raise EmailVerificationRateLimited(
            "Verification email limit reached. Try again later.", hourly_retry,
        )

    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_verification_token(raw_token)
    now = timezone.now()
    timeout_seconds = int(getattr(settings, "EMAIL_VERIFICATION_TIMEOUT", 86400))

    with transaction.atomic():
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        if not locked_user.is_active or locked_user.status != User.Status.ACTIVE:
            raise ValidationError({"detail": ["Account is not active."]})
        if locked_user.email_verified:
            return {"already_verified": True, "email_verified": True}
        EmailVerificationToken.objects.filter(
            user=locked_user, used_at__isnull=True, invalidated_at__isnull=True,
        ).update(invalidated_at=now)
        EmailVerificationToken.objects.create(
            user=locked_user,
            email=(locked_user.email or "").strip().lower(),
            email_version=locked_user.email_version,
            token_hash=token_hash,
            expires_at=now + timedelta(seconds=timeout_seconds),
        )
        target_email = locked_user.email

    link = build_verification_url(raw_token)
    try:
        send_mail(
            "OHAYO - Verify your email address",
            f"Verify your OHAYO email address using this link:\n{link}\n\n"
            f"This link expires in {timeout_seconds // 3600} hours and can only be used once.\n"
            "If you did not request this email, you can safely ignore it.",
            settings.DEFAULT_FROM_EMAIL,
            [target_email],
            fail_silently=False,
        )
    except Exception:
        # Never log raw verification tokens or leak SMTP secrets.
        logger.error("Email verification delivery failed for user %s.", user.pk)
    return {"already_verified": False, "email_verified": False}


@transaction.atomic
def confirm_email_verification(*, token):
    """Verify a one-time hashed token and invoke on_email_verified(user) in the same transaction."""
    invalid = ValidationError({"token": ["Verification link is invalid or expired."]})
    if not isinstance(token, str) or not token.strip() or len(token) > 256:
        raise invalid
    token_hash = hash_verification_token(token.strip())
    record = (
        EmailVerificationToken.objects.select_for_update()
        .filter(token_hash=token_hash)
        .first()
    )
    if record is None:
        raise invalid
    now = timezone.now()
    if record.used_at is not None or record.invalidated_at is not None or record.expires_at <= now:
        raise invalid
    user = User.objects.select_for_update().get(pk=record.user_id)
    if not user.is_active or user.status != User.Status.ACTIVE:
        raise invalid
    if (
        record.email_version != user.email_version
        or record.email.strip().lower() != (user.email or "").strip().lower()
    ):
        record.invalidated_at = now
        record.save(update_fields=["invalidated_at"])
        raise invalid

    record.used_at = now
    record.save(update_fields=["used_at"])
    EmailVerificationToken.objects.filter(
        user=user, used_at__isnull=True, invalidated_at__isnull=True,
    ).update(invalidated_at=now)
    if user.email_verified_at is None:
        user.email_verified_at = now
        user.save(update_fields=["email_verified_at"])
    on_email_verified(user)
    return user
