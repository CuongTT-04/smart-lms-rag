from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase

from apps.users.api.serializers import UserSerializer
from apps.users.models import StudentProfile, TeacherProfile, User


align_profiles = import_module("apps.users.migrations.0003_role_specific_profiles").align_profiles


class RoleProfileTests(TestCase):
    def test_orm_creation_and_serialization_follow_role(self):
        for role in User.Role.values:
            with self.subTest(role=role):
                user = User.objects.create_user(role.lower(), role=role)
                data = UserSerializer(user).data
                self.assertEqual(StudentProfile.objects.filter(user=user).exists(), role == "STUDENT")
                self.assertEqual(TeacherProfile.objects.filter(user=user).exists(), role == "TEACHER")
                self.assertEqual("student_profile" in data, role == "STUDENT")
                self.assertEqual("teacher_profile" in data, role == "TEACHER")

    def test_cleanup_removes_empty_legacy_profiles_and_backfills_missing_profiles(self):
        student = User.objects.create_user("student")
        student.student_profile.learning_goal = "Keep this goal"
        student.student_profile.save()
        TeacherProfile.objects.create(user=student)
        teacher = User.objects.create_user("teacher", role="TEACHER")
        StudentProfile.objects.create(user=teacher)
        TeacherProfile.objects.filter(user=teacher).delete()
        admin = User.objects.create_superuser("admin")
        StudentProfile.objects.create(user=admin)
        TeacherProfile.objects.create(user=admin)
        for _ in range(2):
            align_profiles(apps, SimpleNamespace(connection=connection))
        self.assertEqual(StudentProfile.objects.count(), 1)
        self.assertEqual(TeacherProfile.objects.count(), 1)
        self.assertEqual(StudentProfile.objects.get(user=student).learning_goal, "Keep this goal")
        self.assertTrue(TeacherProfile.objects.filter(user=teacher).exists())

    def test_cleanup_refuses_to_delete_populated_mismatched_profiles(self):
        student = User.objects.create_user("student")
        profile = TeacherProfile.objects.create(user=student, bio="Keep this biography")
        with self.assertRaisesRegex(RuntimeError, "Nonempty profiles"):
            align_profiles(apps, SimpleNamespace(connection=connection))
        self.assertTrue(TeacherProfile.objects.filter(pk=profile.pk).exists())
        TeacherProfile.objects.filter(pk=profile.pk).update(bio="", specialization="Python")
        with self.assertRaises(RuntimeError):
            align_profiles(apps, SimpleNamespace(connection=connection))
        TeacherProfile.objects.filter(pk=profile.pk).delete()
        teacher = User.objects.create_user("teacher", role="TEACHER")
        StudentProfile.objects.create(user=teacher, learning_goal="Keep this goal")
        with self.assertRaises(RuntimeError):
            align_profiles(apps, SimpleNamespace(connection=connection))
