from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", PASSWORD_RESET_PREVIEW=False)
class PasswordResetAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = User.objects.create_user(
            "student", email="student@example.com", password="Old-Ohayo-839!",
            full_name="Student Example",
        )
        self.request_url = reverse("users:password-reset")
        self.confirm_url = reverse("users:password-reset-confirm")
        self.uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.token = default_token_generator.make_token(self.user)
        self.password = "New-Ohayo-Secure-839!"

    def tearDown(self):
        cache.clear()

    def request_reset(self, email="student@example.com"):
        return self.client.post(self.request_url, {"email": email}, format="json")

    def confirm(self, **changes):
        return self.client.post(self.confirm_url, {
            "uid": self.uid, "token": self.token,
            "password": self.password, "password_confirm": self.password, **changes,
        }, format="json")

    def test_complete_email_reset_and_login_flow(self):
        response = self.request_reset("STUDENT@EXAMPLE.COM")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"detail"})
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        link = next(line for line in mail.outbox[0].body.splitlines() if line.startswith("http"))
        values = parse_qs(urlsplit(link).query)
        self.assertTrue(link.startswith(settings.PASSWORD_RESET_URL))
        response = self.confirm(uid=values["uid"][0], token=values["token"][0])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn("access", response.json())
        self.assertEqual(response.cookies[settings.JWT_REFRESH_COOKIE_NAME]["max-age"], 0)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))
        self.assertEqual(self.user.role, "STUDENT")
        login_url = reverse("users:login")
        for password, expected in (("Old-Ohayo-839!", 401), (self.password, 200)):
            login = self.client.post(login_url, {"username": self.user.username, "password": password}, format="json")
            self.assertEqual(login.status_code, expected)

    @override_settings(DEBUG=True, PASSWORD_RESET_PREVIEW=True)
    def test_development_preview_returns_working_link_without_email(self):
        response = self.request_reset()
        self.assertEqual(response.status_code, 200)
        values = parse_qs(urlsplit(response.json()["reset_url"]).query)
        self.assertEqual(self.confirm(uid=values["uid"][0], token=values["token"][0]).status_code, 200)
        self.assertFalse(getattr(mail, "outbox", []))

    @override_settings(DEBUG=False, PASSWORD_RESET_PREVIEW=True)
    def test_production_never_returns_preview_link_even_when_flag_enabled(self):
        response = self.request_reset()
        self.assertNotIn("reset_url", response.json())
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(DEBUG=True, PASSWORD_RESET_PREVIEW=True)
    def test_preview_unknown_account_does_not_return_a_link(self):
        response = self.request_reset("unknown@example.com")
        self.assertNotIn("reset_url", response.json())

    def test_unknown_disabled_and_unusable_accounts_have_identical_responses(self):
        expected = self.request_reset().json()
        User.objects.create_user("blocked", email="blocked@example.com", status="BLOCKED", password="Old-Ohayo-839!")
        User.objects.create_user("inactive", email="inactive@example.com", is_active=False, password="Old-Ohayo-839!")
        User.objects.create_user("unusable", email="unusable@example.com")
        for email in ("unknown@example.com", "blocked@example.com", "inactive@example.com", "unusable@example.com"):
            response = self.request_reset(email)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), expected)
        self.assertEqual(len(mail.outbox), 1)

    def test_delivery_failure_returns_generic_message_without_secrets(self):
        with patch("apps.users.services.send_mail", side_effect=OSError("SMTP unavailable")), self.assertLogs("apps.users.services", level="ERROR"):
            response = self.request_reset()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.token, response.content.decode())

    def test_invalid_request_payloads_are_rejected(self):
        for payload in ({}, {"email": "not-an-email"}, {"email": None}, [], {"email": self.user.email, "role": "ADMIN"}):
            cache.clear()
            response = self.client.post(self.request_url, payload, format="json")
            self.assertEqual(response.status_code, 400)
        self.assertFalse(getattr(mail, "outbox", []))
        self.assertEqual(self.client.get(self.request_url).status_code, 405)
        self.assertEqual(self.client.get(self.confirm_url).status_code, 405)

    def test_invalid_uid_and_tampered_tokens_are_rejected(self):
        for changes in ({"uid": "not-base64"}, {"uid": "%%%"}, {"token": "invalid"}, {"token": self.token + "x"}):
            response = self.confirm(**changes)
            self.assertEqual(response.status_code, 400)
            self.assertIn("token", response.json())
        other = User.objects.create_user("other", email="other@example.com", password="Other-Pass-839!")
        self.assertEqual(self.confirm(uid=urlsafe_base64_encode(force_bytes(other.pk))).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old-Ohayo-839!"))

    def test_expired_token_is_rejected(self):
        with patch.object(default_token_generator, "_now", return_value=default_token_generator._now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 1)):
            response = self.confirm()
        self.assertEqual(response.status_code, 400)

    def test_token_can_only_be_used_once_and_sibling_links_are_invalidated(self):
        with patch.object(default_token_generator, "_now", return_value=default_token_generator._now() + timedelta(seconds=1)):
            sibling = default_token_generator.make_token(self.user)
        self.assertEqual(self.confirm().status_code, 200)
        self.assertEqual(self.confirm().status_code, 400)
        self.assertEqual(self.confirm(token=sibling).status_code, 400)

    def test_password_validation_does_not_consume_token(self):
        for password in ("short", "12345678", "student", "abcdefgh1!", "Abcdefgh!", "Abcdefg1", "Abcdef1 "):
            response = self.confirm(password=password, password_confirm=password)
            self.assertEqual(response.status_code, 400)
            self.assertIn("password", response.json())
        self.assertEqual(self.confirm(password_confirm="different").status_code, 400)
        self.assertEqual(self.confirm().status_code, 200)

    def test_required_fields_and_unexpected_fields(self):
        payload = {"uid": self.uid, "token": self.token, "password": self.password, "password_confirm": self.password}
        for field in payload:
            response = self.client.post(self.confirm_url, {key: value for key, value in payload.items() if key != field}, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.json())
        self.assertEqual(self.confirm(email=self.user.email).status_code, 400)
        self.assertEqual(self.client.post(self.confirm_url, [], format="json").status_code, 400)

    def test_blocked_or_deleted_account_cannot_reset(self):
        self.user.status = "BLOCKED"
        self.user.save(update_fields=["status"])
        self.assertEqual(self.confirm().status_code, 400)
        self.user.delete()
        self.assertEqual(self.confirm().status_code, 400)

    def test_password_whitespace_is_preserved(self):
        password = f"  {self.password}  "
        self.assertEqual(self.confirm(password=password, password_confirm=password).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(password))
        self.assertFalse(self.user.check_password(password.strip()))

    def test_reset_revokes_all_old_access_refresh_and_session_tokens(self):
        refreshes = [RefreshToken.for_user(self.user), RefreshToken.for_user(self.user)]
        access = str(refreshes[0].access_token)
        self.assertEqual(self.confirm().status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.get(reverse("users:me")).status_code, 401)
        self.client.credentials()
        for refresh in refreshes:
            self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
            self.assertEqual(self.client.get(reverse("users:session")).json(), {"authenticated": False})
            self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
            self.assertEqual(self.client.post(reverse("users:token-refresh")).status_code, 401)

    def test_direct_password_change_also_invalidates_jwts(self):
        refresh = RefreshToken.for_user(self.user)
        self.user.set_password(self.password)
        self.user.save(update_fields=["password"])
        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
        self.assertEqual(self.client.get(reverse("users:session")).json(), {"authenticated": False})
        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
        self.assertEqual(self.client.post(reverse("users:token-refresh")).status_code, 401)

    def test_request_email_limit_is_case_insensitive(self):
        for email in (self.user.email, self.user.email.upper(), self.user.email):
            self.assertEqual(self.request_reset(email).status_code, 200)
        self.assertEqual(self.request_reset(self.user.email.upper()).status_code, 429)
        self.assertEqual(len(mail.outbox), 3)

    def test_request_ip_and_confirmation_limits(self):
        for index in range(5):
            self.assertEqual(self.request_reset(f"unknown{index}@example.com").status_code, 200)
        self.assertEqual(self.request_reset("another@example.com").status_code, 429)
        for _ in range(20):
            self.assertEqual(self.confirm(token="bad-token").status_code, 400)
        response = self.confirm(token="bad-token")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    def test_request_uses_configured_url_not_untrusted_host(self):
        response = self.client.post(self.request_url, {"email": self.user.email}, format="json", HTTP_HOST="testserver")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("http://testserver", mail.outbox[0].body)

    def test_token_revocation_failure_rolls_back_password_change(self):
        RefreshToken.for_user(self.user)
        with patch("apps.users.services.BlacklistedToken.objects.get_or_create", side_effect=RuntimeError("Storage unavailable")):
            with self.assertRaises(RuntimeError):
                self.confirm()
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old-Ohayo-839!"))
        self.assertTrue(default_token_generator.check_token(self.user, self.token))

    def test_teacher_and_admin_can_reset_without_changing_role_or_profiles(self):
        for role in ("TEACHER", "ADMIN"):
            user = User.objects.create_user(role.lower(), role=role, email=f"{role.lower()}@example.com", password="Old-Ohayo-839!")
            response = self.confirm(
                uid=urlsafe_base64_encode(force_bytes(user.pk)),
                token=default_token_generator.make_token(user),
            )
            self.assertEqual(response.status_code, 200)
            user.refresh_from_db()
            self.assertEqual(user.role, role)
            self.assertTrue(user.check_password(self.password))
            self.assertEqual(hasattr(user, "teacher_profile"), role == "TEACHER")
            self.assertFalse(hasattr(user, "student_profile"))
