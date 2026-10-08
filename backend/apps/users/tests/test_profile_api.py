from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError as APIValidationError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import StudentProfile, TeacherProfile, User
from apps.users.services import update_user_profile
from common.testing import authenticate_client


PASSWORD = "Old-Ohayo-839!"
NEW_PASSWORD = "New-Ohayo-849!"


class UserProfileAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("student", email="student@example.com", password=PASSWORD, full_name="Original name")
        self.other = User.objects.create_user("other", email="other@example.com", password=PASSWORD)
        self.client = authenticate_client(APIClient(enforce_csrf_checks=True), self.user)
        self.url = reverse("users:me")

    def update(self, payload):
        return self.client.patch(self.url, payload, format="json")

    def test_student_updates_account_and_profile_atomically(self):
        profile_id = self.user.student_profile.pk
        response = self.update({
            "username": "new_student", "email": "NEW@example.com", "current_password": PASSWORD,
            "full_name": "Nguyễn Minh Anh", "avatar_url": "https://example.com/avatar.png",
            "phone": "+84901234567", "student_profile": {"learning_goal": "Learn Python"},
        })
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertFalse(body["requires_login"])
        self.assertEqual(body["user"]["email"], "new@example.com")
        self.assertEqual(body["user"]["username"], "new_student")
        self.assertEqual(body["user"]["full_name"], "Nguyễn Minh Anh")
        self.assertEqual(body["user"]["phone"], "+84901234567")
        self.assertEqual(body["user"]["avatar_url"], "https://example.com/avatar.png")
        self.assertEqual(body["user"]["student_profile"]["id"], str(profile_id))
        self.assertEqual(body["user"]["student_profile"]["learning_goal"], "Learn Python")
        self.assertNotIn("teacher_profile", body["user"])
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.other.refresh_from_db()
        self.assertEqual(self.other.full_name, "")

    def test_teacher_updates_only_matching_profile_and_retains_unspecified_fields(self):
        teacher = User.objects.create_user("teacher", role="TEACHER", password=PASSWORD)
        teacher.teacher_profile.specialization = "Python"
        teacher.teacher_profile.save()
        authenticate_client(self.client, teacher)
        response = self.update({"teacher_profile": {"bio": "Python instructor"}})
        self.assertEqual(response.status_code, 200)
        profile = response.json()["user"]["teacher_profile"]
        self.assertEqual(profile["bio"], "Python instructor")
        self.assertEqual(profile["specialization"], "Python")
        self.assertNotIn("student_profile", response.json()["user"])
        self.assertFalse(StudentProfile.objects.filter(user=teacher).exists())

    def test_optional_fields_can_be_cleared(self):
        response = self.update({"avatar_url": "", "phone": "", "student_profile": {"learning_goal": ""}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["phone"], "")
        self.assertEqual(response.json()["user"]["student_profile"]["learning_goal"], "")

    def test_partial_update_does_not_clear_other_fields(self):
        response = self.update({"full_name": "Updated name"})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "student")
        self.assertEqual(self.user.email, "student@example.com")
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_same_identifiers_and_case_only_changes_do_not_conflict_with_self(self):
        response = self.update({"username": "STUDENT", "email": "STUDENT@EXAMPLE.COM"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["email"], "student@example.com")

    def test_duplicates_are_rejected_without_partial_update(self):
        for field, value in (("username", "OTHER"), ("email", "OTHER@EXAMPLE.COM")):
            response = self.update({field: value, "full_name": "Must not save", "current_password": PASSWORD})
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.json())
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Original name")

    def test_email_change_requires_current_password_and_invalidates_old_reset_link(self):
        token = default_token_generator.make_token(self.user)
        for values in ({}, {"current_password": "Wrong-password1!"}):
            response = self.update({"email": "new@example.com", **values})
            self.assertEqual(response.status_code, 400)
            self.assertIn("current_password", response.json())
        self.assertEqual(self.update({"email": "new@example.com", "current_password": PASSWORD}).status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(default_token_generator.check_token(self.user, token))

    def test_password_change_hashes_password_and_revokes_all_old_jwts(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
        token = default_token_generator.make_token(self.user)
        response = self.update({"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD, "current_password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["requires_login"])
        self.assertEqual(response.cookies[settings.JWT_REFRESH_COOKIE_NAME]["max-age"], 0)
        for field in ("password", "passwordHash", "password_confirm", "current_password", "access"):
            self.assertNotIn(field, response.json()["user"])
            self.assertNotIn(field, response.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertNotEqual(self.user.password, NEW_PASSWORD)
        self.assertTrue(BlacklistedToken.objects.filter(token__user=self.user).exists())
        self.assertFalse(default_token_generator.check_token(self.user, token))
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
        self.assertEqual(self.client.get(reverse("users:session")).json(), {"authenticated": False})
        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
        self.assertEqual(self.client.post(reverse("users:token-refresh")).status_code, 401)
        self.client.credentials()
        for password, expected in ((PASSWORD, 401), (NEW_PASSWORD, 200)):
            login = self.client.post(reverse("users:login"), {"username": self.user.username, "password": password}, format="json")
            self.assertEqual(login.status_code, expected)

    def test_invalid_password_change_does_not_save_any_fields(self):
        for payload in (
            {"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
            {"password": NEW_PASSWORD, "password_confirm": "mismatch", "current_password": PASSWORD},
            {"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD, "current_password": "incorrect"},
            *({"password": value, "password_confirm": value, "current_password": PASSWORD} for value in (
                "short", "abcdefgh1!", "Abcdefgh!", "Abcdefg1", "Abcdef1 ",
            )),
        ):
            self.assertEqual(self.update({"full_name": "Must not save", **payload}).status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Original name")
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_password_spaces_are_preserved(self):
        password = f"  {NEW_PASSWORD}  "
        self.assertEqual(self.update({"password": password, "password_confirm": password, "current_password": PASSWORD}).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(password))
        self.assertFalse(self.user.check_password(password.strip()))

    def test_protected_fields_and_direct_hashes_are_rejected(self):
        for field, value in {
            "role": "TEACHER", "status": "BLOCKED", "is_staff": True, "is_superuser": True,
            "is_active": False, "id": str(self.other.pk), "user_id": str(self.other.pk),
            "passwordHash": "hash", "password_hash": "hash", "groups": [], "created_at": "2026-01-01",
        }.items():
            response = self.update({field: value, "full_name": "Must not save"})
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.json())
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, "STUDENT")
        self.assertEqual(self.user.full_name, "Original name")

    def test_wrong_role_profile_and_profile_metadata_are_rejected(self):
        for payload in (
            {"teacher_profile": {"bio": "Forbidden"}},
            {"student_profile": {"id": str(self.other.pk)}},
            {"student_profile": {"user_id": str(self.other.pk)}},
            {"student_profile": {"created_at": "2026-01-01"}},
            {"student_profile": {"bio": "Forbidden"}},
        ):
            self.assertEqual(self.update(payload).status_code, 400)
        teacher = User.objects.create_user("teacher", role="TEACHER", password=PASSWORD)
        authenticate_client(self.client, teacher)
        self.assertEqual(self.update({"student_profile": {"learning_goal": "Forbidden"}}).status_code, 400)
        self.assertEqual(self.update({"teacher_profile": {"learning_goal": "Forbidden"}}).status_code, 400)

    def test_admin_can_update_identity_but_not_student_or_teacher_profile(self):
        admin = User.objects.create_superuser("admin", password=PASSWORD)
        authenticate_client(self.client, admin)
        self.assertEqual(self.update({"full_name": "Admin name"}).status_code, 200)
        for key in ("student_profile", "teacher_profile"):
            self.assertEqual(self.update({key: {"learning_goal": "Forbidden", "bio": "Forbidden"}}).status_code, 400)

    def test_empty_invalid_and_overlong_inputs(self):
        for payload in (
            {}, [], {"student_profile": {}}, {"student_profile": None},
            {"username": "invalid username"}, {"username": " "}, {"email": "bad"}, {"email": ""},
            {"full_name": " "}, {"full_name": "x" * 256}, {"phone": "abc"}, {"phone": None},
            {"avatar_url": "javascript:alert(1)"}, {"student_profile": {"learning_goal": "x" * 5001}},
            {"password_confirm": NEW_PASSWORD}, {"current_password": PASSWORD},
        ):
            self.assertEqual(self.update(payload).status_code, 400, payload)
        teacher = User.objects.create_user("teacher", role="TEACHER", password=PASSWORD)
        authenticate_client(self.client, teacher)
        for values in ({"bio": "x" * 5001}, {"specialization": "x" * 256}, {}):
            self.assertEqual(self.update({"teacher_profile": values}).status_code, 400)

    def test_authentication_is_required_and_put_is_not_supported(self):
        self.client.credentials()
        self.assertEqual(self.update({"full_name": "Forbidden"}).status_code, 401)
        authenticate_client(self.client, self.user)
        self.assertEqual(self.client.put(self.url, {"full_name": "No PUT"}, format="json").status_code, 405)
        User.objects.filter(pk=self.user.pk).update(status="BLOCKED", is_active=False)
        self.assertEqual(self.update({"full_name": "Forbidden"}).status_code, 401)

    def test_profile_storage_failure_rolls_back_account_and_password(self):
        with patch.object(StudentProfile, "save", side_effect=RuntimeError("Profile failed")):
            with self.assertRaises(RuntimeError):
                self.update({"full_name": "Must not save", "student_profile": {"learning_goal": "New goal"}})
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Original name")

    def test_service_revalidates_role_and_password_under_lock(self):
        User.objects.filter(pk=self.user.pk).update(role="TEACHER")
        with self.assertRaises(APIValidationError):
            update_user_profile(actor=self.user, changes={"student_profile": {"learning_goal": "Forbidden"}})
        User.objects.filter(pk=self.user.pk).update(password="changed-password-hash")
        with self.assertRaises(PermissionDenied):
            update_user_profile(actor=self.user, changes={"full_name": "Forbidden"})

    def test_missing_matching_profile_is_recreated_on_update(self):
        StudentProfile.objects.filter(user=self.user).delete()
        response = self.update({"student_profile": {"learning_goal": "Restored profile"}})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(StudentProfile.objects.filter(user=self.user).exists())
        self.assertFalse(TeacherProfile.objects.filter(user=self.user).exists())

    def test_password_revocation_failure_rolls_back_everything(self):
        RefreshToken.for_user(self.user)
        with patch("apps.users.services.revoke_refresh_tokens", side_effect=RuntimeError("Storage unavailable")):
            with self.assertRaises(RuntimeError):
                self.update({"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD, "current_password": PASSWORD, "student_profile": {"learning_goal": "Must not save"}})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))
        self.assertEqual(self.user.student_profile.learning_goal, "")
