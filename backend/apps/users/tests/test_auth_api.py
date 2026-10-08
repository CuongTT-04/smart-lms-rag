from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import AccessToken


User = get_user_model()
PASSWORD = "Auth-Test-Password-839!"


class AuthenticationAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "teacher", password=PASSWORD, email="teacher@example.com",
            full_name="Teacher A", role=User.Role.TEACHER,
        )
        self.client = APIClient()
        self.login_url = reverse("users:login")
        self.refresh_url = reverse("users:token-refresh")
        self.session_url = reverse("users:session")
        self.logout_url = reverse("users:logout")
        self.me_url = reverse("users:me")

    def login(self, username="teacher", password=PASSWORD):
        return self.client.post(
            self.login_url, {"username": username, "password": password}, format="json"
        )

    def authorize(self, access):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_complete_jwt_flow_rotates_refresh_and_revokes_on_logout(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"user", "access"})
        self.assertTrue(body["access"])
        self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, response.cookies)
        refresh_before = response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
        self.assertTrue(response.cookies[settings.JWT_REFRESH_COOKIE_NAME]["httponly"])
        self.assertIn("no-store", response["Cache-Control"])

        self.authorize(body["access"])
        me = self.client.get(self.me_url)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"], body["user"])
        self.assertEqual(
            set(me.json()["user"]),
            {"id", "username", "email", "full_name", "avatar_url", "phone", "role", "status",
             "created_at", "updated_at", "last_login", "teacher_profile"},
        )

        refreshed = self.client.post(self.refresh_url)
        self.assertEqual(refreshed.status_code, 200)
        self.assertTrue(refreshed.json()["access"])
        self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, refreshed.cookies)
        refresh_after = refreshed.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
        self.assertNotEqual(refresh_before, refresh_after)
        self.assertTrue(BlacklistedToken.objects.exists())

        self.authorize(refreshed.json()["access"])
        logout = self.client.post(self.logout_url)
        self.assertEqual(logout.status_code, 204)
        self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, logout.cookies)
        self.assertGreaterEqual(BlacklistedToken.objects.count(), 2)
        self.assertEqual(self.client.post(self.refresh_url).status_code, 401)

    def test_login_does_not_require_csrf_and_cannot_access_removed_endpoint(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get("/api/users/csrf/").status_code, 404)

    def test_session_restores_a_refresh_cookie_without_401_for_anonymous_visitors(self):
        anonymous = self.client.get(self.session_url)
        self.assertEqual(anonymous.status_code, 200)
        self.assertEqual(anonymous.json(), {"authenticated": False})

        login = self.login()
        session = self.client.get(self.session_url)
        self.assertEqual(session.status_code, 200)
        self.assertTrue(session.json()["authenticated"])
        self.assertEqual(session.json()["user"], login.json()["user"])
        self.assertTrue(session.json()["access"])

        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = "not-a-jwt"
        invalid = self.client.get(self.session_url)
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(invalid.json(), {"authenticated": False})
        self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, invalid.cookies)

    def test_invalid_credentials_and_disabled_accounts_share_error(self):
        User.objects.create_user("blocked", password=PASSWORD, status=User.Status.BLOCKED)
        User.objects.create_user("inactive", password=PASSWORD, status=User.Status.INACTIVE)
        cases = (
            ("teacher", "wrong-password"), ("unknown", PASSWORD),
            ("blocked", PASSWORD), ("inactive", PASSWORD),
        )
        messages = []
        for username, password in cases:
            with self.subTest(username=username):
                response = self.login(username, password)
                self.assertEqual(response.status_code, 401)
                messages.append(response.json())
                self.assertNotIn(settings.JWT_REFRESH_COOKIE_NAME, response.cookies)
        self.assertTrue(all(message == messages[0] for message in messages))

    def test_login_validates_input_and_preserves_password_whitespace(self):
        for payload in ({}, {"username": "teacher"}, {"username": "", "password": ""}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(self.login_url, payload, format="json").status_code, 400)
        password = "  Auth-Test-Password-839!  "
        self.user.set_password(password)
        self.user.save(update_fields=["password"])
        self.assertEqual(self.login(password=password.strip()).status_code, 401)
        self.assertEqual(self.login(password=password).status_code, 200)

    def test_protected_endpoints_require_bearer_token_and_reject_basic_auth(self):
        self.assertEqual(self.client.get(self.me_url).status_code, 401)
        self.assertEqual(self.client.post(self.logout_url).status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Basic dGVhY2hlcjp0ZXN0")
        self.assertEqual(self.client.get(self.me_url).status_code, 401)

    def test_disabled_account_loses_access_and_cannot_refresh(self):
        response = self.login()
        self.authorize(response.json()["access"])
        self.user.status = User.Status.BLOCKED
        self.user.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.me_url).status_code, 401)
        self.assertEqual(self.client.post(self.refresh_url).status_code, 401)

    @override_settings(SIMPLE_JWT={**settings.SIMPLE_JWT, "ACCESS_TOKEN_LIFETIME": timedelta(seconds=-1)})
    def test_expired_access_token_is_rejected(self):
        expired = AccessToken.for_user(self.user)
        expired.set_exp(lifetime=timedelta(seconds=-1))
        self.authorize(str(expired))
        self.assertEqual(self.client.get(self.me_url).status_code, 401)

    def test_method_restrictions_and_refresh_requires_cookie(self):
        self.assertEqual(self.client.get(self.login_url).status_code, 405)
        self.assertEqual(self.client.get(self.refresh_url).status_code, 405)
        self.assertEqual(self.client.post(self.refresh_url).status_code, 401)
        login = self.login()
        self.assertEqual(login.status_code, 200)
        self.authorize(login.json()["access"])
        self.assertEqual(self.client.get(self.logout_url).status_code, 405)
        self.assertEqual(self.client.post(self.me_url).status_code, 405)
