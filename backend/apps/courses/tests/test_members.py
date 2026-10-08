import uuid

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.courses.models import CourseMember, Enrollment
from apps.courses.services import create_course
from apps.users.models import User
from common.testing import authenticate_client


class MemberAPITests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("owner", role="TEACHER")
        self.other = User.objects.create_user("other", role="TEACHER")
        self.student = User.objects.create_user("student")
        self.course = create_course(actor=self.teacher, title="Course")
        self.member = CourseMember.objects.create(course=self.course, user=self.student)
        self.enrollment = Enrollment.objects.create(classroom=self.course.classrooms.get(), student=self.student.student_profile)
        self.client = authenticate_client(APIClient(), self.teacher)
        self.list_url = reverse("courses:members", args=[self.course.pk])
        self.url = reverse("courses:member-revoke", args=[self.course.pk, self.member.pk])

    def test_direct_grant_endpoint_removed(self):
        self.assertEqual(self.client.post(self.list_url, {"user_id": str(self.student.pk)}, format="json").status_code, 405)

    def test_list_and_idempotent_revoke_withdraw_enrollment(self):
        listing = self.client.get(self.list_url)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["count"], 2)
        self.assertIn("no-store", listing["Cache-Control"])
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.member.refresh_from_db()
        self.enrollment.refresh_from_db()
        removed_at = self.member.removed_at
        self.assertEqual(self.member.status, "REMOVED")
        self.assertEqual(self.enrollment.status, "WITHDRAWN")
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.member.refresh_from_db()
        self.assertEqual(self.member.removed_at, removed_at)

    def test_member_list_is_paginated_and_scoped(self):
        for index in range(21):
            user = User.objects.create_user(f"student{index}")
            CourseMember.objects.create(course=self.course, user=user)
        other_course = create_course(actor=self.other, title="Other")
        outside = CourseMember.objects.create(course=other_course, user=self.student)
        first = self.client.get(self.list_url).json()
        second = self.client.get(self.list_url, {"page": 2}).json()
        self.assertEqual(first["count"], 23)
        self.assertEqual(len(first["results"]), 20)
        self.assertEqual(len(second["results"]), 3)
        self.assertNotIn(str(outside.pk), [m["id"] for m in first["results"] + second["results"]])

    def test_only_active_owner_can_list_and_revoke(self):
        admin = User.objects.create_superuser("admin")
        for user in [self.other, self.student, admin]:
            authenticate_client(self.client, user)
            self.assertEqual(self.client.get(self.list_url).status_code, 403)
            self.assertEqual(self.client.delete(self.url).status_code, 403)
        authenticate_client(self.client, self.teacher)
        owner = self.course.memberships.get(role="OWNER")
        for status in ["SUSPENDED", "REMOVED"]:
            owner.status = status
            owner.save()
            self.assertEqual(self.client.get(self.list_url).status_code, 403)

    def test_owner_and_other_course_members_cannot_be_revoked(self):
        owner = self.course.memberships.get(role="OWNER")
        self.assertEqual(self.client.delete(reverse("courses:member-revoke", args=[self.course.pk, owner.pk])).status_code, 400)
        other_course = create_course(actor=self.other, title="Other")
        outside = CourseMember.objects.create(course=other_course, user=self.student)
        for member_id in [outside.pk, uuid.uuid4()]:
            self.assertEqual(self.client.delete(reverse("courses:member-revoke", args=[self.course.pk, member_id])).status_code, 404)
        outside.refresh_from_db()
        self.assertEqual(outside.status, "ACTIVE")

    def test_legacy_non_student_members_cannot_be_revoked(self):
        for role in ["TEACHER", "ASSISTANT"]:
            legacy = CourseMember.objects.create(course=self.course, user=self.other, role=role, status="REMOVED")
            self.assertEqual(self.client.delete(reverse("courses:member-revoke", args=[self.course.pk, legacy.pk])).status_code, 400)
            legacy.delete()

    def test_anonymous_and_unsupported_methods(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.patch(self.list_url, {}, format="json").status_code, 405)
        self.client.credentials()
        self.assertEqual(self.client.get(self.list_url).status_code, 401)
        self.assertEqual(self.client.delete(self.url).status_code, 401)
