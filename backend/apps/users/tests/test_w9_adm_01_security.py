"""W9-ADM-01 tests: email verification + hook, auth_version revocation, CSRF and login rate limits."""
from datetime import timedelta
import re
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.notifications.consumers import NotificationConsumer
from apps.notifications.tickets import issue_ticket
from apps.users.email_verification import (
    register_email_verified_hook, unregister_email_verified_hook,
)
from apps.users.models import EmailVerificationToken
from apps.users.services import bump_auth_version
from common.testing import authenticate_client


User = get_user_model()
PASSWORD = "Adm01-Test-Password-941!"


def _extract_token_from_mail(message):
    match = re.search(r"https?://\S+", message.body)
    assert match is not None, f"No verification link found in: {message.body}"
    parsed = urlparse(match.group(0))
    return parsed, parse_qs(parsed.query)["token"][0]


class EmailVerificationTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.user = User.objects.create_user(
            "teacher_unverified", email="teacher@ptit.edu.vn", password=PASSWORD,
            full_name="Giao vien PTIT", role=User.Role.TEACHER,
        )
        self.client = authenticate_client(APIClient(), self.user)
        self.send_url = reverse("users:email-verification-send")
        self.confirm_url = reverse("users:email-verification-confirm")
        self.me_url = reverse("users:me")

    def tearDown(self):
        cache.clear()

    def test_send_confirm_one_time_hashed_token_and_transactional_hook(self):
        hook_calls = []

        def on_verified(verified_user):
            hook_calls.append((verified_user.pk, verified_user.email_verified))

        register_email_verified_hook(on_verified)
        self.addCleanup(unregister_email_verified_hook, on_verified)

        # Different Host header must never override configured EMAIL_VERIFICATION_URL origin.
        sent = self.client.post(self.send_url, HTTP_HOST="127.0.0.1:9999")
        self.assertEqual(sent.status_code, 200, sent.content)
        self.assertEqual(len(mail.outbox), 1)
        parsed, raw_token = _extract_token_from_mail(mail.outbox[0])
        self.assertNotEqual(parsed.netloc, "127.0.0.1:9999")
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", settings.EMAIL_VERIFICATION_URL)

        record = EmailVerificationToken.objects.get(user=self.user)
        self.assertNotEqual(record.token_hash, raw_token)
        self.assertEqual(len(record.token_hash), 64)

        confirm = APIClient().post(self.confirm_url, {"token": raw_token}, format="json")
        self.assertEqual(confirm.status_code, 200, confirm.content)
        self.assertTrue(confirm.json()["email_verified"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertEqual(hook_calls, [(self.user.pk, True)])

        # Replay of the same token fails and does not re-run hook.
        replay = APIClient().post(self.confirm_url, {"token": raw_token}, format="json")
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(len(hook_calls), 1)

        # Profile API exposes email_verified=True and blocks client tampering.
        me = self.client.get(self.me_url).json()["user"]
        self.assertTrue(me["email_verified"])
        self.assertIsNotNone(me["email_verified_at"])
        tamper = self.client.patch(self.me_url, {"email_verified": False}, format="json")
        self.assertEqual(tamper.status_code, 400)

    def test_resend_invalidates_previous_token_and_enforces_cooldown_and_hourly_limit(self):
        first = self.client.post(self.send_url)
        self.assertEqual(first.status_code, 200)
        _, first_token = _extract_token_from_mail(mail.outbox[-1])

        # Immediate resend hits 60s cooldown with Retry-After.
        too_soon = self.client.post(self.send_url)
        self.assertEqual(too_soon.status_code, 429)
        self.assertIn("Retry-After", too_soon)

        # Clear cooldown only (simulating 61s passing) and resend twice more -> 3/hour succeeds, 4th fails.
        with override_settings(EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS=0):
            cache.clear()
            for _ in range(3):
                self.assertEqual(self.client.post(self.send_url).status_code, 200)
            fourth = self.client.post(self.send_url)
            self.assertEqual(fourth.status_code, 429)
            self.assertIn("Retry-After", fourth)

        _, latest_token = _extract_token_from_mail(mail.outbox[-1])
        self.assertNotEqual(first_token, latest_token)
        self.assertEqual(APIClient().post(self.confirm_url, {"token": first_token}, format="json").status_code, 400)
        self.assertEqual(APIClient().post(self.confirm_url, {"token": latest_token}, format="json").status_code, 200)

    def test_expired_token_and_email_change_invalidation(self):
        self.assertEqual(self.client.post(self.send_url).status_code, 200)
        _, raw_token = _extract_token_from_mail(mail.outbox[-1])

        # Expire token beyond 24h.
        EmailVerificationToken.objects.filter(user=self.user).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(APIClient().post(self.confirm_url, {"token": raw_token}, format="json").status_code, 400)

        # Issue fresh token, then change email -> old token invalidated & email_verified stays False.
        cache.clear()
        self.assertEqual(self.client.post(self.send_url).status_code, 200)
        _, token_before_change = _extract_token_from_mail(mail.outbox[-1])
        patch = self.client.patch(
            self.me_url,
            {"email": "changed@example.com", "current_password": PASSWORD},
            format="json",
        )
        self.assertEqual(patch.status_code, 200, patch.content)
        self.assertFalse(patch.json()["user"]["email_verified"])
        self.assertEqual(APIClient().post(self.confirm_url, {"token": token_before_change}, format="json").status_code, 400)


class AuthVersionRevocationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            "student_revoked", email="student-revoked@example.com", password=PASSWORD,
            full_name="Hoc vien", role=User.Role.STUDENT,
        )
        self.client = APIClient()
        self.login_url = reverse("users:login")
        self.me_url = reverse("users:me")
        self.refresh_url = reverse("users:token-refresh")
        self.session_url = reverse("users:session")

    def tearDown(self):
        cache.clear()

    def test_lock_then_unlock_keeps_old_tokens_permanently_revoked(self):
        login = self.client.post(self.login_url, {"username": self.user.username, "password": PASSWORD}, format="json")
        self.assertEqual(login.status_code, 200)
        old_access = login.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        self.assertEqual(self.client.get(self.me_url).status_code, 200)

        # Lock then unlock -> auth_version bumped so old access/refresh/session remain invalid!
        self.user.status = User.Status.BLOCKED
        self.user.save(update_fields=["status"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.auth_version, 2)
        self.assertEqual(self.client.get(self.me_url).status_code, 401)

        self.user.status = User.Status.ACTIVE
        self.user.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.me_url).status_code, 401)
        self.assertEqual(self.client.post(self.refresh_url).status_code, 401)
        self.assertEqual(self.client.get(self.session_url).json(), {"authenticated": False})

    def test_role_change_and_bump_auth_version_invalidate_tokens_and_ws_session(self):
        login = self.client.post(self.login_url, {"username": self.user.username, "password": PASSWORD}, format="json")
        old_access = login.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")

        # Changing role immediately revokes existing access & refresh tokens.
        self.user.role = User.Role.TEACHER
        self.user.save(update_fields=["role"])
        self.assertEqual(self.client.get(self.me_url).status_code, 401)
        self.assertEqual(self.client.post(self.refresh_url).status_code, 401)

        # Re-login and verify bump_auth_version invalidates both HTTP & WebSocket active check.
        login2 = self.client.post(self.login_url, {"username": self.user.username, "password": PASSWORD}, format="json")
        self.assertEqual(login2.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login2.json()['access']}")
        consumer = NotificationConsumer()
        consumer.user_id = str(self.user.pk)
        consumer.auth_version = self.user.auth_version
        self.assertTrue(consumer.is_active_user())

        bump_auth_version(self.user, close_sockets=False)
        self.assertEqual(self.client.get(self.me_url).status_code, 401)
        self.assertFalse(consumer.is_active_user())

        # Verify issue_ticket embeds current auth_version (mocking redis).
        from unittest.mock import Mock, patch
        redis_mock = Mock()
        with patch("apps.notifications.tickets.redis_client", return_value=redis_mock):
            self.user.refresh_from_db()
            issue_ticket(self.user, {"exp": int(timezone.now().timestamp()) + 300})
        stored_json = redis_mock.set.call_args[0][1]
        self.assertIn(f'"auth_version": {self.user.auth_version}', stored_json)


class CsrfAndLoginRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            "csrf_student", email="csrf@example.com", password=PASSWORD,
            full_name="CSRF Student", role=User.Role.STUDENT,
        )
        self.csrf_url = reverse("users:csrf")
        self.session_url = reverse("users:session")
        self.login_url = reverse("users:login")
        self.refresh_url = reverse("users:token-refresh")
        self.logout_url = reverse("users:logout")
        self.me_url = reverse("users:me")

    def tearDown(self):
        cache.clear()

    def test_csrf_enforced_full_chain_login_f5_refresh_logout_and_blocks_missing_or_evil_origin(self):
        client = APIClient(enforce_csrf_checks=True)
        # Missing CSRF on login is blocked with 403 CSRF_FAILED.
        no_csrf = client.post(self.login_url, {"username": self.user.username, "password": PASSWORD}, format="json")
        self.assertEqual(no_csrf.status_code, 403)
        self.assertEqual(no_csrf.json()["code"], "CSRF_FAILED")

        # Bootstrap CSRF via GET /api/users/session/ (same as App.jsx boot).
        boot = client.get(self.session_url)
        self.assertEqual(boot.status_code, 200)
        csrf_token = boot.cookies["csrftoken"].value

        # Untrusted cross-origin Origin header is blocked even with valid CSRF token.
        evil = client.post(
            self.login_url,
            {"username": self.user.username, "password": PASSWORD},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
            HTTP_ORIGIN="https://evil.example",
        )
        self.assertEqual(evil.status_code, 403)
        self.assertEqual(evil.json()["code"], "CSRF_FAILED")

        # Valid login with CSRF + trusted Origin succeeds and rotates csrftoken.
        trusted_origin = "http://localhost:5173"
        login = client.post(
            self.login_url,
            {"username": self.user.username, "password": PASSWORD},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
            HTTP_ORIGIN=trusted_origin,
        )
        self.assertEqual(login.status_code, 200, login.content)
        rotated_csrf = client.cookies["csrftoken"].value

        # F5 session restore works and keeps session alive.
        restored = client.get(self.session_url)
        self.assertEqual(restored.status_code, 200)
        self.assertTrue(restored.json()["authenticated"])

        # Refresh without CSRF is blocked (403); refresh with rotated CSRF succeeds (200).
        bad_refresh = client.post(self.refresh_url, HTTP_ORIGIN=trusted_origin)
        self.assertEqual(bad_refresh.status_code, 403)
        self.assertEqual(bad_refresh.json()["code"], "CSRF_FAILED")

        refreshed = client.post(self.refresh_url, HTTP_X_CSRFTOKEN=rotated_csrf, HTTP_ORIGIN=trusted_origin)
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        new_access = refreshed.json()["access"]

        # Logout without CSRF is blocked; logout with CSRF + bearer succeeds (204).
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
        bad_logout = client.post(self.logout_url, HTTP_ORIGIN=trusted_origin)
        self.assertEqual(bad_logout.status_code, 403)
        good_logout = client.post(self.logout_url, HTTP_X_CSRFTOKEN=rotated_csrf, HTTP_ORIGIN=trusted_origin)
        self.assertEqual(good_logout.status_code, 204)

    @override_settings(LOGIN_MAX_ATTEMPTS_PER_ACCOUNT=3, LOGIN_MAX_ATTEMPTS_PER_IP=50)
    def test_login_account_rate_limit_returns_429_without_permanently_locking_account(self):
        client = APIClient()
        for attempt in range(3):
            resp = client.post(
                self.login_url,
                {"username": "CSRF_Student" if attempt % 2 else "csrf_student", "password": "wrong-password"},
                format="json",
            )
            self.assertEqual(resp.status_code, 401)
        throttled = client.post(
            self.login_url, {"username": "csrf_student", "password": PASSWORD}, format="json",
        )
        self.assertEqual(throttled.status_code, 429)
        self.assertIn("Retry-After", throttled)
        # Account itself is NOT permanently locked in DB.
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.ACTIVE)
        self.assertTrue(self.user.is_active)

    @override_settings(LOGIN_MAX_ATTEMPTS_PER_ACCOUNT=50, LOGIN_MAX_ATTEMPTS_PER_IP=3)
    def test_login_ip_rate_limit_returns_429_with_retry_after(self):
        client = APIClient()
        for idx in range(3):
            resp = client.post(
                self.login_url, {"username": f"unknown_{idx}", "password": "wrong"}, format="json",
            )
            self.assertEqual(resp.status_code, 401)
        throttled = client.post(
            self.login_url, {"username": "csrf_student", "password": PASSWORD}, format="json",
        )
        self.assertEqual(throttled.status_code, 429)
        self.assertIn("Retry-After", throttled)

    def test_production_settings_enforce_secure_defaults(self):
        from config.settings import base, production
        self.assertFalse(production.PASSWORD_RESET_PREVIEW)
        self.assertTrue(production.CSRF_COOKIE_SECURE)
        self.assertTrue(production.JWT_REFRESH_COOKIE_SECURE)
        self.assertEqual(base.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT, 10)
        self.assertEqual(base.LOGIN_ACCOUNT_WINDOW_SECONDS, 900)
        self.assertEqual(base.LOGIN_MAX_ATTEMPTS_PER_IP, 30)
        self.assertEqual(base.LOGIN_IP_WINDOW_SECONDS, 60)
        self.assertEqual(base.EMAIL_VERIFICATION_MAX_PER_HOUR, 3)
        self.assertEqual(base.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS, 60)
