from apps.courses.models import Classroom
from unittest.mock import patch
import uuid

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.courses.models import AccessPolicy, Classroom, Course, CourseMember, Enrollment, JoinRequest
from apps.courses.services import create_course, update_course
from apps.users.models import User
from common.testing import authenticate_client


class EnrollmentAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("owner", role="TEACHER")
        self.other = User.objects.create_user("other", role="TEACHER")
        self.student = User.objects.create_user("student")
        self.second_student = User.objects.create_user("second")
        self.course = create_course(actor=self.owner, title="Python")
        self.course = update_course(actor=self.owner, course=self.course, changes={"status": "PUBLISHED"})
        self.classroom = Classroom.objects.create(course=self.course, name=self.course.title)
        self.client = authenticate_client(APIClient(), self.student)
        self.teacher = authenticate_client(APIClient(), self.owner)

    def join(self, **payload):
        return self.client.post(reverse("courses:join"), {"class_code": self.classroom.class_code, **payload}, format="json")

    def approval(self):
        self.classroom.require_approval = True
        self.classroom.save()

    def review(self, request_id, decision="approve", **extra):
        return self.teacher.post(reverse("courses:request-review", args=[self.course.pk, request_id]), {"decision": decision, **extra}, format="json")

    def test_default_class_and_policy_and_unique_code(self):
        self.assertEqual(len(self.classroom.class_code), 12)
        self.assertEqual(self.course.access_policy.access_type, "FREE")
        self.assertFalse(self.course.access_policy.require_approval)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Classroom.objects.create(course=self.course, name="Duplicate", class_code=self.classroom.class_code)

    def test_direct_join_creates_membership_and_enrollment_without_request(self):
        response = self.join(class_code=self.classroom.class_code.lower())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["status"], "ENROLLED")
        self.assertIsNone(response.json()["join_request"])
        self.assertFalse(JoinRequest.objects.exists())
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(self.client.get(reverse("courses:update", args=[self.course.pk])).status_code, 200)
        repeat = self.join()
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat.json()["enrollment"]["id"], response.json()["enrollment"]["id"])
        self.assertNotIn("class_code", response.json()["enrollment"])

    def test_pending_then_approval_grants_access_atomically(self):
        self.approval()
        response = self.join(message="Please admit me")
        self.assertEqual(response.status_code, 201)
        request_id = response.json()["join_request"]["id"]
        self.assertEqual(response.json()["status"], "PENDING")
        self.assertFalse(Enrollment.objects.exists())
        self.assertFalse(CourseMember.objects.filter(user=self.student).exists())
        self.assertEqual(self.client.get(reverse("courses:update", args=[self.course.pk])).status_code, 403)
        repeat = self.join()
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat.json()["join_request"]["id"], request_id)
        approved = self.review(request_id, review_note="Welcome")
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "APPROVED")
        self.assertEqual(approved.json()["reviewed_by_id"], str(self.owner.pk))
        self.assertIsNotNone(approved.json()["reviewed_at"])
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(self.client.get(reverse("courses:update", args=[self.course.pk])).status_code, 200)
        self.assertEqual(self.review(request_id).json(), approved.json())
        self.assertEqual(self.review(request_id, "reject").status_code, 400)

    def test_reject_keeps_access_denied_and_allows_a_new_application(self):
        self.approval()
        request_id = self.join().json()["join_request"]["id"]
        rejected = self.review(request_id, "reject", review_note="Not this class")
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["review_note"], "Not this class")
        self.assertEqual(self.review(request_id, "reject").status_code, 200)
        self.assertEqual(self.review(request_id).status_code, 400)
        self.assertFalse(Enrollment.objects.exists())
        self.assertFalse(CourseMember.objects.filter(user=self.student).exists())
        new = self.join()
        self.assertEqual(new.status_code, 201)
        self.assertNotEqual(new.json()["join_request"]["id"], request_id)

    def test_cancel_is_own_pending_only(self):
        self.approval()
        request_id = self.join().json()["join_request"]["id"]
        url = reverse("courses:request-cancel", args=[request_id])
        authenticate_client(self.client, self.second_student)
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 404)
        authenticate_client(self.client, self.student)
        self.assertEqual(self.client.post(url, {}, format="json").json()["status"], "CANCELED")
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 200)
        self.assertEqual(self.review(request_id).status_code, 400)
        self.assertEqual(self.join().status_code, 201)

    def test_closed_unpublished_and_paid_courses_rejected(self):
        for state in ["DRAFT", "ARCHIVED"]:
            self.course.status = state
            self.course.save()
            self.assertEqual(self.join().status_code, 400)
        self.course.status = "PUBLISHED"
        self.course.save()
        self.classroom.is_join_enabled = False
        self.classroom.save()
        self.assertEqual(self.join().status_code, 400)
        self.classroom.is_join_enabled = True
        self.classroom.save()
        policy = self.course.access_policy
        policy.access_type = "PAID"
        policy.price = 100
        policy.save()
        self.assertEqual(self.join().status_code, 400)
        self.assertFalse(Enrollment.objects.exists())

    def test_owner_unavailable_rejects_join(self):
        self.course.memberships.filter(role="OWNER").update(status="SUSPENDED")
        self.assertEqual(self.join().status_code, 400)

    def test_invalid_codes_extra_fields_and_wrong_roles(self):
        for payload in [{}, {"class_code": "bad"}, {"class_code": "FFFFFFFFFFFF"}, {"class_code": self.classroom.class_code, "student_id": str(self.second_student.pk)}]:
            self.assertEqual(self.client.post(reverse("courses:join"), payload, format="json").status_code, 400)
        for user in [self.owner, User.objects.create_superuser("admin")]:
            authenticate_client(self.client, user)
            self.assertEqual(self.join().status_code, 403)
        self.client.credentials()
        self.assertEqual(self.join().status_code, 401)

    def test_owner_only_classroom_and_policy_management(self):
        url = reverse("courses:policy", args=[self.course.pk])
        response = self.teacher.patch(url, {"require_approval": True}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["require_approval"])
        for payload in [{}, {"price": 100}, {"access_type": "PAID"}, {"require_class_code": False}]:
            self.assertEqual(self.teacher.patch(url, payload, format="json").status_code, 400)
        classrooms = reverse("courses:classrooms", args=[self.course.pk])
        created = self.teacher.post(classrooms, {"name": "Evening class"}, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertNotEqual(created.json()["class_code"], self.classroom.class_code)
        self.assertEqual(self.teacher.get(classrooms).json()["count"], 2)
        update = reverse("courses:classroom-update", args=[self.course.pk, created.json()["id"]])
        self.assertEqual(self.teacher.patch(update, {"is_join_enabled": False}, format="json").status_code, 200)
        self.assertEqual(self.teacher.patch(update, {"class_code": "AAAAAAAAAAAA"}, format="json").status_code, 400)
        self.assertEqual(self.client.get(classrooms).status_code, 403)
        self.assertEqual(self.client.patch(url, {"require_approval": False}, format="json").status_code, 403)
        authenticate_client(self.teacher, self.other)
        self.assertEqual(self.teacher.get(classrooms).status_code, 403)
        self.assertEqual(self.teacher.patch(update, {"name": "Stolen"}, format="json").status_code, 403)

    def test_review_is_owner_scoped_and_request_scoped(self):
        self.approval()
        request_id = self.join().json()["join_request"]["id"]
        authenticate_client(self.teacher, self.other)
        self.assertEqual(self.review(request_id).status_code, 403)
        other_course = create_course(actor=self.other, title="Other")
        url = reverse("courses:request-review", args=[other_course.pk, request_id])
        self.assertEqual(self.teacher.post(url, {"decision": "approve"}, format="json").status_code, 404)
        authenticate_client(self.teacher, self.owner)
        self.assertEqual(self.review(uuid.uuid4()).status_code, 404)
        self.assertEqual(self.review(request_id, "invalid").status_code, 400)

    def test_review_rechecks_classroom_course_and_student_status(self):
        self.approval()
        request_id = self.join().json()["join_request"]["id"]
        self.classroom.is_join_enabled = False
        self.classroom.save()
        self.assertEqual(self.review(request_id).status_code, 400)
        self.classroom.is_join_enabled = True
        self.classroom.save()
        self.student.status = "BLOCKED"
        self.student.save()
        self.assertEqual(self.review(request_id).status_code, 400)
        self.assertEqual(JoinRequest.objects.get(pk=request_id).status, "PENDING")
        self.assertFalse(Enrollment.objects.exists())
        self.assertEqual(self.review(request_id, "reject").status_code, 200)

    def test_lists_are_paginated_and_private(self):
        self.approval()
        request_id = self.join().json()["join_request"]["id"]
        requests_url = reverse("courses:requests", args=[self.course.pk])
        response = self.teacher.get(requests_url, {"status": "PENDING"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(self.teacher.get(requests_url, {"status": "BAD"}).status_code, 400)
        self.assertEqual(self.client.get(requests_url).status_code, 403)
        mine = reverse("courses:requests-mine")
        self.assertEqual(self.client.get(mine).json()["count"], 1)
        authenticate_client(self.client, self.second_student)
        self.assertEqual(self.client.get(mine).json()["count"], 0)
        self.assertEqual(self.review(request_id).status_code, 200)
        enrollments = reverse("courses:enrollments-mine")
        self.assertEqual(self.client.get(enrollments).json()["count"], 0)
        authenticate_client(self.client, self.student)
        self.assertEqual(self.client.get(enrollments).json()["count"], 1)

    def test_revoked_students_need_approval_even_in_open_courses(self):
        self.join()
        member = CourseMember.objects.get(user=self.student, course=self.course)
        self.teacher.delete(reverse("courses:member-revoke", args=[self.course.pk, member.pk]))
        response = self.join()
        self.assertEqual(response.json()["status"], "PENDING")
        member.refresh_from_db()
        self.assertEqual(member.status, "REMOVED")
        self.assertEqual(self.review(response.json()["join_request"]["id"]).status_code, 200)
        member.refresh_from_db()
        self.assertEqual(member.status, "ACTIVE")
        self.assertIsNone(member.removed_at)

    def test_pending_requests_not_bypassed_when_policy_changes(self):
        self.approval()
        request_id = self.join().json()["join_request"]["id"]
        Classroom.objects.filter(course=self.course).update(require_approval=False)
        self.assertEqual(self.join().json()["join_request"]["id"], request_id)
        self.assertFalse(Enrollment.objects.exists())

    def test_approval_rolls_back_membership_when_enrollment_fails(self):
        self.approval()
        request_id = self.join().json()["join_request"]["id"]
        with patch("apps.courses.enrollment_services.Enrollment.objects.get_or_create", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                self.review(request_id)
        self.assertEqual(JoinRequest.objects.get(pk=request_id).status, "PENDING")
        self.assertFalse(CourseMember.objects.filter(user=self.student).exists())

    def test_one_pending_request_constraint_and_no_invited_status(self):
        self.approval()
        self.join()
        with self.assertRaises(IntegrityError), transaction.atomic():
            JoinRequest.objects.create(student=self.student, classroom=self.classroom)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseMember.objects.create(course=self.course, user=self.second_student, status="INVITED")

    def test_class_code_attempts_are_throttled(self):
        for _ in range(30):
            self.assertEqual(self.join(class_code="FFFFFFFFFFFF").status_code, 400)
        self.assertEqual(self.join(class_code="FFFFFFFFFFFF").status_code, 429)
