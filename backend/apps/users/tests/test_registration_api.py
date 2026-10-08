from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.courses.models import CourseMember
from apps.courses.services import create_course
from apps.users.services import register_user
from django.core.exceptions import ValidationError
from apps.users.models import StudentProfile, TeacherProfile, User


class RegistrationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.url = reverse("users:register")
        self.payload = {
            "username": "new_student", "email": "New.Student@example.com",
            "password": "Ohayo-Registration-839!", "password_confirm": "Ohayo-Registration-839!",
            "full_name": "New Student", "phone": "+84901234567",
            "role": "STUDENT",
            "avatar_url": "https://example.com/avatar.png", "learning_goal": "Learn Python",
        }

    def register(self, **changes):
        return self.client.post(self.url, {**self.payload, **changes}, format="json")

    def test_registration_creates_complete_student_and_supports_jwt_login(self):
        response = self.register()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        user = User.objects.get(username="new_student")
        self.assertEqual(body["user"]["id"], str(user.pk))
        self.assertEqual(user.email, "new.student@example.com")
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertEqual(user.status, User.Status.ACTIVE)
        self.assertTrue(user.check_password(self.payload["password"]))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.student_profile.learning_goal, "Learn Python")
        self.assertFalse(TeacherProfile.objects.filter(user=user).exists())
        self.assertNotIn("teacher_profile", body["user"])
        self.assertEqual(user.phone, self.payload["phone"])
        self.assertEqual(user.avatar_url, self.payload["avatar_url"])
        self.assertIn("created_at", body["user"])
        self.assertNotIn("password", body["user"])
        self.assertNotIn("password_confirm", body["user"])
        self.assertNotIn("access", body)
        self.assertNotIn(settings.JWT_REFRESH_COOKIE_NAME, response.cookies)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(CourseMember.objects.filter(user=user).exists())

        login = self.client.post(reverse("users:login"), {
            "username": user.username, "password": self.payload["password"],
        }, format="json")
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
        me = self.client.get(reverse("users:me"))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["student_profile"]["learning_goal"], "Learn Python")
        self.assertEqual(self.client.get(reverse("courses:create")).json()["count"], 0)
        denied = self.client.post(reverse("courses:create"), {"title": "Forbidden"}, format="json")
        self.assertEqual(denied.status_code, 403)

    def test_teacher_registration_populates_profile_and_grants_only_own_course_access(self):
        response = self.register(role="TEACHER", learning_goal="", bio="Python instructor", specialization="Python")
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(username="new_student")
        self.assertEqual(response.json()["user"]["role"], "TEACHER")
        self.assertEqual(user.teacher_profile.bio, "Python instructor")
        self.assertEqual(user.teacher_profile.specialization, "Python")
        self.assertFalse(StudentProfile.objects.filter(user=user).exists())
        self.assertNotIn("student_profile", response.json()["user"])
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(CourseMember.objects.filter(user=user).exists())
        login = self.client.post(reverse("users:login"), {
            "username": user.username, "password": self.payload["password"],
        }, format="json")
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["role"], "TEACHER")
        self.assertNotIn("student_profile", login.json()["user"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
        created = self.client.post(reverse("courses:create"), {"title": "My course"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertTrue(CourseMember.objects.filter(user=user, role=CourseMember.Role.OWNER).exists())
        other = User.objects.create_user("other_teacher", role=User.Role.TEACHER)
        course = create_course(actor=other, title="Other course")
        url = f"/api/courses/{course.pk}/"
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.patch(url, {"title": "Forbidden"}, format="json").status_code, 403)

    def test_invalid_roles_and_incompatible_profiles_are_rejected(self):
        for role in ("ADMIN", "UNASSIGNED", "student", "", None):
            with self.subTest(role=role):
                response = self.register(role=role)
                self.assertEqual(response.status_code, 400)
                self.assertIn("role", response.json())
        for changes, field in (
            ({"role": "TEACHER"}, "learning_goal"),
            ({"specialization": "Python"}, "specialization"),
            ({"bio": "x" * 5001}, "bio"),
            ({"specialization": "x" * 256}, "specialization"),
        ):
            response = self.register(**changes)
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.json())
        self.assertFalse(User.objects.exists())

    def test_teacher_registration_accepts_empty_optional_profiles(self):
        payload = {key: value for key, value in self.payload.items() if key != "learning_goal"}
        payload["role"] = "TEACHER"
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get().teacher_profile.bio, "")

    def test_service_rejects_privileged_roles_before_creating_user(self):
        payload = {key: value for key, value in self.payload.items() if key != "password_confirm"}
        for role in ("ADMIN", None, "UNASSIGNED"):
            with self.subTest(role=role), self.assertRaises(ValidationError):
                register_user(**{**payload, "role": role})
        self.assertFalse(User.objects.exists())

    def test_registration_cannot_change_an_existing_account_role(self):
        self.assertEqual(self.register().status_code, 201)
        response = self.register(role="TEACHER", learning_goal="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.get().role, User.Role.STUDENT)

    def test_registration_rejects_privilege_and_teacher_profile_fields(self):
        for field, value in {
            "role": "ADMIN", "status": "BLOCKED", "is_staff": True,
            "is_superuser": True, "is_active": True, "id": "custom-id",
            "teacher_profile": {"specialization": "Python"}, "bio": "Teacher",
            "groups": [], "passwordHash": "hashed",
        }.items():
            with self.subTest(field=field):
                response = self.register(**{field: value})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())
        self.assertFalse(User.objects.exists())
        self.assertFalse(StudentProfile.objects.exists())

    def test_identifiers_are_unique_even_with_different_case(self):
        self.assertEqual(self.register().status_code, 201)
        for changes, field in (
            ({"username": "NEW_STUDENT", "email": "other@example.com"}, "username"),
            ({"username": "other", "email": "NEW.STUDENT@EXAMPLE.COM"}, "email"),
        ):
            response = self.register(**changes)
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.json())
        self.assertEqual(User.objects.count(), 1)
        for changes in (
            {"username": "NEW_STUDENT", "email": "other@example.com"},
            {"username": "other", "email": "NEW.STUDENT@EXAMPLE.COM"},
        ):
            with self.assertRaises(IntegrityError), transaction.atomic():
                User.objects.create_user(**changes)

    def test_invalid_registration_does_not_create_partial_accounts(self):
        for changes in (
            {"username": "invalid username"}, {"email": "not-an-email"}, {"full_name": "  "},
            {"password_confirm": "different"}, {"password": "12345678", "password_confirm": "12345678"},
            {"password": "short", "password_confirm": "short"}, {"phone": "abc"},
            *({"password": password, "password_confirm": password} for password in (
                "abcdefgh1!", "Abcdefgh!", "Abcdefg1", "Abcdef1 ",
            )),
            {"avatar_url": "javascript:alert(1)"}, {"learning_goal": "x" * 5001},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.register(**changes).status_code, 400)
        for field in ("username", "email", "password", "password_confirm", "full_name", "role"):
            payload = {key: value for key, value in self.payload.items() if key != field}
            self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        self.assertFalse(User.objects.exists())
        self.assertFalse(StudentProfile.objects.exists())
        self.assertFalse(TeacherProfile.objects.exists())

    def test_optional_fields_and_password_whitespace(self):
        payload = {key: value for key, value in self.payload.items() if key not in ("avatar_url", "phone", "learning_goal")}
        payload.update(password="  Ohayo-Registration-839!  ", password_confirm="  Ohayo-Registration-839!  ")
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        user = User.objects.get()
        self.assertTrue(user.check_password(payload["password"]))
        self.assertFalse(user.check_password(payload["password"].strip()))
        self.assertEqual(user.phone, "")
        self.assertEqual(user.student_profile.learning_goal, "")

    def test_profile_failure_rolls_back_user(self):
        with patch.object(StudentProfile, "save", side_effect=RuntimeError("Profile storage failed")):
            with self.assertRaises(RuntimeError):
                self.register()
        self.assertFalse(User.objects.exists())
        self.assertFalse(StudentProfile.objects.exists())

    def test_database_role_change_does_not_expose_old_profile_or_grant_course_access(self):
        self.assertEqual(self.register().status_code, 201)
        User.objects.filter(username="new_student").update(role=User.Role.TEACHER)
        user = User.objects.get()
        from apps.users.api.serializers import UserSerializer
        self.assertNotIn("student_profile", UserSerializer(user).data)
        self.assertFalse(TeacherProfile.objects.filter(user=user).exists())
        self.assertEqual(user.role, User.Role.TEACHER)
        self.assertFalse(user.is_staff)
        self.assertFalse(CourseMember.objects.filter(user=user).exists())

    def test_unsupported_method_and_non_object_body(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.url, [], format="json").status_code, 400)
