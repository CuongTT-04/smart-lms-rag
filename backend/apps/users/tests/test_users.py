import uuid

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.users.forms import CustomUserChangeForm, CustomUserCreationForm


User = get_user_model()
PASSWORD = "Demo-Test-Password-839!"


class UserModelTests(TestCase):
    def test_default_user_has_uuid_and_hashed_password(self):
        user = User.objects.create_user("student", password=PASSWORD)
        self.assertIsInstance(user.pk, uuid.UUID)
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertEqual(user.status, User.Status.ACTIVE)
        self.assertTrue(user.is_active)
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_superuser_is_active_admin(self):
        user = User.objects.create_superuser("admin", password=PASSWORD)
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertEqual(user.status, User.Status.ACTIVE)
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_superuser_rejects_wrong_role_or_status(self):
        for extra_fields in (
            {"role": User.Role.STUDENT},
            {"status": User.Status.BLOCKED},
            {"is_active": False},
        ):
            with self.subTest(extra_fields=extra_fields), self.assertRaises(ValueError):
                User.objects.create_superuser("admin", password=PASSWORD, **extra_fields)

    def test_inactive_creation_maps_to_inactive_status(self):
        user = User.objects.create_user("inactive", password=PASSWORD, is_active=False)
        self.assertEqual(user.status, User.Status.INACTIVE)
        self.assertFalse(user.is_active)

    def test_conflicting_account_flags_are_rejected(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(
                "conflict", status=User.Status.BLOCKED, is_active=True
            )

    def test_status_changes_control_authentication(self):
        user = User.objects.create_user("student", password=PASSWORD)
        self.assertIsNotNone(authenticate(username="student", password=PASSWORD))
        for status in (User.Status.BLOCKED, User.Status.INACTIVE):
            with self.subTest(status=status):
                user.status = status
                user.save(update_fields=["status"])
                user.refresh_from_db()
                self.assertFalse(user.is_active)
                self.assertIsNone(authenticate(username="student", password=PASSWORD))
        user.status = User.Status.ACTIVE
        user.save(update_fields=["status"])
        self.assertIsNotNone(authenticate(username="student", password=PASSWORD))

    def test_database_rejects_bulk_update_with_conflicting_status(self):
        user = User.objects.create_user("student", password=PASSWORD)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=user.pk).update(status=User.Status.BLOCKED)
        user.refresh_from_db()
        self.assertEqual(user.status, User.Status.ACTIVE)

    def test_partial_profile_update_preserves_concurrent_status_change(self):
        user = User.objects.create_user("student", password=PASSWORD)
        User.objects.filter(pk=user.pk).update(
            status=User.Status.BLOCKED, is_active=False
        )
        user.full_name = "Updated Student"
        user.save(update_fields=["full_name"])
        user.refresh_from_db()
        self.assertEqual(user.status, User.Status.BLOCKED)
        self.assertFalse(user.is_active)


class UserAdminTests(TestCase):
    def test_creation_form_uses_custom_user_and_preserves_blocked_status(self):
        form = CustomUserCreationForm(
            data={
                "username": "blocked",
                "email": "blocked@example.com",
                "full_name": "Blocked Student",
                "role": User.Role.STUDENT,
                "status": User.Status.BLOCKED,
                "password1": PASSWORD,
                "password2": PASSWORD,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.get_full_name(), "Blocked Student")
        self.assertFalse(user.is_active)
        self.assertTrue(user.check_password(PASSWORD))

    def test_change_form_unblocks_user(self):
        user = User.objects.create_user(
            "blocked", password=PASSWORD, status=User.Status.BLOCKED
        )
        form = CustomUserChangeForm(
            instance=user,
            data={
                "username": user.username,
                "email": "blocked@example.com",
                "full_name": "Unblocked Student",
                "role": User.Role.STUDENT,
                "status": User.Status.ACTIVE,
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(PASSWORD))

    def test_admin_add_and_change_pages_support_custom_user(self):
        admin = User.objects.create_superuser("admin", password=PASSWORD)
        self.client.force_login(admin)
        response = self.client.get(reverse("admin:users_user_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="full_name"')
        self.assertNotContains(response, 'name="role"')
        self.assertContains(response, 'name="status"')
        response = self.client.post(
            reverse("admin:users_user_add"),
            {
                "username": "teacher",
                "email": "teacher@example.com",
                "full_name": "Teacher A",
                "role": User.Role.TEACHER,
                "status": User.Status.ACTIVE,
                "password1": PASSWORD,
                "password2": PASSWORD,
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        teacher = User.objects.get(username="teacher")
        self.assertTrue(teacher.check_password(PASSWORD))
        self.assertFalse(teacher.is_staff)
        self.assertEqual(teacher.role, User.Role.STUDENT)
        response = self.client.get(reverse("admin:users_user_change", args=[teacher.pk]))
        self.assertEqual(response.status_code, 200)

    def test_admin_cannot_change_role_with_a_forged_post(self):
        admin = User.objects.create_superuser("admin", password=PASSWORD)
        student = User.objects.create_user("student", password=PASSWORD)
        self.client.force_login(admin)
        response = self.client.post(reverse("admin:users_user_change", args=[student.pk]), {
            "username": student.username, "email": "student@example.com",
            "full_name": "Student", "role": "TEACHER", "status": "ACTIVE", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        student.refresh_from_db()
        self.assertEqual(student.role, User.Role.STUDENT)
