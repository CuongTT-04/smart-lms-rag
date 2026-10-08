import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.courses.models import Course, CourseMember
from apps.courses.permissions import can_manage_course
from apps.courses.services import create_course, update_course
from common.testing import authenticate_client


User = get_user_model()


class CourseServiceTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("teacher", role=User.Role.TEACHER)

    def test_creation_assigns_active_owner_and_defaults_to_draft(self):
        course = create_course(actor=self.teacher, title="  New Course  ")
        self.assertIsInstance(course.pk, uuid.UUID)
        self.assertEqual(course.title, "New Course")
        self.assertEqual(course.status, Course.Status.DRAFT)
        self.assertIsNone(course.published_at)
        member = course.memberships.get()
        self.assertEqual(member.user, self.teacher)
        self.assertEqual(member.role, CourseMember.Role.OWNER)
        self.assertEqual(member.status, CourseMember.Status.ACTIVE)

    def test_owner_creation_failure_rolls_back_course(self):
        with patch.object(CourseMember, "save", side_effect=IntegrityError("Failed")):
            with self.assertRaises(IntegrityError):
                create_course(actor=self.teacher, title="Rolled Back")
        self.assertFalse(Course.objects.exists())
        self.assertFalse(CourseMember.objects.exists())

    def test_creation_service_rejects_empty_titles_without_side_effects(self):
        for title in (None, "", "   ", "x" * 256):
            with self.subTest(title=title), self.assertRaises(ValidationError):
                create_course(actor=self.teacher, title=title)
        self.assertFalse(Course.objects.exists())

    def test_services_enforce_role_and_scope(self):
        student = User.objects.create_user("student")
        other = User.objects.create_user("other", role=User.Role.TEACHER)
        with self.assertRaises(PermissionDenied):
            create_course(actor=student, title="Forbidden")
        course = create_course(actor=self.teacher, title="Original")
        with self.assertRaises(PermissionDenied):
            update_course(actor=other, course=course, changes={"title": "Forbidden"})
        course.refresh_from_db()
        self.assertEqual(course.title, "Original")

    def test_database_rejects_duplicate_membership(self):
        course = create_course(actor=self.teacher, title="Course")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseMember.objects.create(course=course, user=self.teacher)
        self.assertEqual(course.memberships.count(), 1)

    def test_database_rejects_second_owner_and_coteachers(self):
        course = create_course(actor=self.teacher, title="Single owner")
        other = User.objects.create_user("other", role=User.Role.TEACHER)
        for role in (CourseMember.Role.OWNER, CourseMember.Role.TEACHER, CourseMember.Role.ASSISTANT):
            with self.subTest(role=role), self.assertRaises(IntegrityError), transaction.atomic():
                CourseMember.objects.create(course=course, user=other, role=role)
        self.assertEqual(course.memberships.count(), 1)

    def test_first_publication_timestamp_survives_status_changes(self):
        course = create_course(actor=self.teacher, title="Course")
        course = update_course(
            actor=self.teacher, course=course, changes={"status": Course.Status.PUBLISHED}
        )
        first_publication = course.published_at
        self.assertIsNotNone(first_publication)
        for status in (Course.Status.ARCHIVED, Course.Status.DRAFT, Course.Status.PUBLISHED):
            course = update_course(actor=self.teacher, course=course, changes={"status": status})
            self.assertEqual(course.published_at, first_publication)

    def test_invalid_service_changes_are_not_persisted(self):
        course = create_course(actor=self.teacher, title="Original")
        for changes in ({}, {"title": "   "}, {"status": "INVALID"}, {"published_at": None}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                update_course(actor=self.teacher, course=course, changes=changes)
            course.refresh_from_db()
            self.assertEqual(course.title, "Original")
            self.assertEqual(course.status, Course.Status.DRAFT)

    def test_management_requires_active_membership_and_account(self):
        course = create_course(actor=self.teacher, title="Course")
        owner = course.memberships.get()
        self.assertTrue(can_manage_course(self.teacher, course))
        for status in (CourseMember.Status.SUSPENDED, CourseMember.Status.REMOVED):
            owner.status = status
            owner.save(update_fields=["status"])
            self.assertFalse(can_manage_course(self.teacher, course))
        owner.status = CourseMember.Status.ACTIVE
        owner.save(update_fields=["status"])
        self.teacher.status = User.Status.BLOCKED
        self.teacher.save(update_fields=["status"])
        self.assertFalse(can_manage_course(self.teacher, course))


class CourseAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("teacher", role=User.Role.TEACHER)
        cls.other = User.objects.create_user("other", role=User.Role.TEACHER)
        cls.student = User.objects.create_user("student")
        cls.admin = User.objects.create_superuser("admin")
        cls.course = create_course(actor=cls.teacher, title="Original", description="Initial")

    def setUp(self):
        self.client = APIClient()
        self.create_url = reverse("courses:create")
        self.update_url = reverse("courses:update", args=[self.course.pk])
        self.login_as(self.teacher)

    def login_as(self, user):
        authenticate_client(self.client, user)

    def test_teacher_can_create_and_patch_information_and_status(self):
        response = self.client.post(
            self.create_url, {"title": "  New Course  ", "description": "Overview"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        course = Course.objects.get(pk=response.json()["id"])
        self.assertEqual(course.title, "New Course")
        self.assertEqual(course.status, Course.Status.DRAFT)
        self.assertEqual(course.memberships.get().user_id, self.teacher.pk)
        response = self.client.patch(
            self.update_url, {"title": "Updated", "description": "", "status": "PUBLISHED"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()["published_at"])
        self.course.refresh_from_db()
        self.assertEqual(self.course.title, "Updated")
        self.assertEqual(self.course.description, "")
        self.assertEqual(self.course.status, Course.Status.PUBLISHED)

    def test_creation_rejects_invalid_titles_and_protected_fields(self):
        for payload in (
            {}, {"title": ""}, {"title": "  "}, {"title": "x" * 256},
            {"title": "Course", "status": "PUBLISHED"},
            {"title": "Course", "user_id": str(self.other.pk)},
            {"title": "Course", "owner": str(self.other.pk)},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(self.create_url, payload, format="json").status_code, 400)
        self.assertEqual(Course.objects.count(), 1)

    def test_only_teacher_role_can_create(self):
        for user in (self.student, self.admin):
            with self.subTest(role=user.role):
                self.login_as(user)
                self.assertEqual(
                    self.client.post(self.create_url, {"title": "Forbidden"}, format="json").status_code, 403
                )
        self.assertEqual(Course.objects.count(), 1)

    def test_anonymous_and_missing_bearer_requests_are_denied(self):
        anonymous = APIClient()
        self.assertEqual(anonymous.post(self.create_url, {"title": "Course"}).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post(self.create_url, {"title": "Course"}).status_code, 401)
        self.assertEqual(self.client.patch(self.update_url, {"title": "Changed"}).status_code, 401)

    def test_partial_update_preserves_unspecified_fields(self):
        self.assertEqual(self.client.patch(self.update_url, {"title": "Updated"}, format="json").status_code, 200)
        self.course.refresh_from_db()
        self.assertEqual(self.course.description, "Initial")
        self.assertEqual(self.course.status, Course.Status.DRAFT)

    def test_patch_rejects_invalid_or_immutable_fields(self):
        for payload in (
            {}, {"title": " "}, {"status": "INVALID"}, {"description": None},
            {"id": str(uuid.uuid4())}, {"published_at": None}, {"role": "OWNER"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.patch(self.update_url, payload, format="json").status_code, 400)
        self.course.refresh_from_db()
        self.assertEqual(self.course.title, "Original")

    def test_unrelated_teacher_student_and_admin_cannot_patch(self):
        CourseMember.objects.create(course=self.course, user=self.student)
        for user in (self.other, self.student, self.admin):
            with self.subTest(role=user.role):
                self.login_as(user)
                self.assertEqual(
                    self.client.patch(self.update_url, {"title": "Forbidden"}, format="json").status_code, 403
                )
        self.course.refresh_from_db()
        self.assertEqual(self.course.title, "Original")

    def test_legacy_teacher_memberships_do_not_allow_management(self):
        member = CourseMember.objects.create(course=self.course, user=self.other, role=CourseMember.Role.TEACHER, status=CourseMember.Status.REMOVED)
        self.login_as(self.other)
        self.assertEqual(self.client.patch(self.update_url, {"title": "Co-taught"}, format="json").status_code, 403)
        for role in (CourseMember.Role.ASSISTANT, CourseMember.Role.STUDENT):
            member.role = role
            member.save(update_fields=["role"])
            self.assertEqual(self.client.patch(self.update_url, {"title": "Forbidden"}, format="json").status_code, 403)

    def test_membership_removal_and_account_blocking_revoke_management(self):
        member = self.course.memberships.get(user=self.teacher)
        member.status = CourseMember.Status.REMOVED
        member.save(update_fields=["status"])
        self.assertEqual(self.client.patch(self.update_url, {"title": "Forbidden"}, format="json").status_code, 403)
        member.status = CourseMember.Status.ACTIVE
        member.save(update_fields=["status"])
        self.teacher.status = User.Status.BLOCKED
        self.teacher.save(update_fields=["status"])
        self.assertEqual(self.client.patch(self.update_url, {"title": "Forbidden"}, format="json").status_code, 401)

    def test_archiving_preserves_data_and_teacher_management(self):
        self.assertEqual(self.client.patch(self.update_url, {"status": "ARCHIVED"}, format="json").status_code, 200)
        self.course.refresh_from_db()
        self.assertEqual(self.course.status, Course.Status.ARCHIVED)
        self.assertEqual(self.course.memberships.count(), 1)
        self.assertEqual(self.client.patch(self.update_url, {"description": "Archived notes"}, format="json").status_code, 200)

    def test_missing_course_and_unsupported_methods(self):
        url = reverse("courses:update", args=[uuid.uuid4()])
        self.assertEqual(self.client.patch(url, {"title": "Course"}, format="json").status_code, 404)
        self.assertEqual(self.client.patch("/api/courses/not-a-uuid/", {}).status_code, 404)
        self.assertEqual(self.client.get(self.create_url).status_code, 200)
        self.assertEqual(self.client.get(self.update_url).status_code, 200)
        self.assertEqual(self.client.put(self.update_url, {}).status_code, 405)
        self.assertEqual(self.client.delete(self.update_url).status_code, 405)

    def test_admin_can_inspect_but_cannot_bypass_services(self):
        # Django Admin intentionally remains on Django's own session + CSRF flow.
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin:courses_course_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:courses_coursemember_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:courses_course_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:courses_coursemember_add")).status_code, 403)
        url = reverse("admin:courses_course_change", args=[self.course.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"title": "Forbidden"}).status_code, 403)
