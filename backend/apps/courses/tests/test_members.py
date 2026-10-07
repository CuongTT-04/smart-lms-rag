import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.courses.api.serializers import CourseMemberSerializer
from apps.courses.models import Course, CourseMember
from apps.courses.permissions import can_view_course
from apps.courses.selectors import list_course_members
from apps.courses.services import (
    create_course, grant_student_access, revoke_student_access, update_course,
)
from common.testing import authenticate_client


User = get_user_model()


class MemberServiceTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("teacher", role=User.Role.TEACHER)
        self.other = User.objects.create_user("other", role=User.Role.TEACHER)
        self.student = User.objects.create_user("student")
        self.course = create_course(actor=self.teacher, title="Course")

    def grant(self):
        return grant_student_access(actor=self.teacher, course=self.course, user_id=self.student.pk)

    def test_grant_revoke_and_regrant_preserve_membership_and_access_rules(self):
        self.course = update_course(
            actor=self.teacher, course=self.course, changes={"status": Course.Status.PUBLISHED}
        )
        self.assertFalse(can_view_course(self.student, self.course))
        member, created = self.grant()
        self.assertTrue(created)
        joined_at = member.joined_at
        self.assertTrue(can_view_course(self.student, self.course))
        repeat, created = self.grant()
        self.assertFalse(created)
        self.assertEqual(repeat.pk, member.pk)
        removed = revoke_student_access(actor=self.teacher, course=self.course, member_id=member.pk)
        self.assertFalse(can_view_course(self.student, self.course))
        repeat = revoke_student_access(actor=self.teacher, course=self.course, member_id=member.pk)
        self.assertEqual(repeat.removed_at, removed.removed_at)
        restored, created = self.grant()
        self.assertFalse(created)
        self.assertEqual(restored.pk, member.pk)
        self.assertEqual(restored.joined_at, joined_at)
        self.assertIsNone(restored.removed_at)
        self.assertTrue(can_view_course(self.student, self.course))
        self.assertEqual(self.course.memberships.count(), 2)

    def test_services_recheck_actor_permissions(self):
        member, _ = self.grant()
        for actor in (self.other, self.student):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                grant_student_access(actor=actor, course=self.course, user_id=self.student.pk)
            with self.assertRaises(PermissionDenied):
                revoke_student_access(actor=actor, course=self.course, member_id=member.pk)
        member.refresh_from_db()
        self.assertEqual(member.status, CourseMember.Status.ACTIVE)

    def test_invalid_student_accounts_are_rejected_without_membership_changes(self):
        admin = User.objects.create_superuser("admin")
        targets = [uuid.uuid4(), self.teacher.pk, admin.pk]
        for status in (User.Status.BLOCKED, User.Status.INACTIVE):
            user = User.objects.create_user(status.lower(), status=status)
            targets.append(user.pk)
        for user_id in targets:
            with self.subTest(user_id=user_id), self.assertRaises(ValidationError):
                grant_student_access(actor=self.teacher, course=self.course, user_id=user_id)
        self.assertEqual(self.course.memberships.count(), 1)

    def test_grant_never_demotes_existing_non_student_membership(self):
        for role in (CourseMember.Role.TEACHER, CourseMember.Role.ASSISTANT):
            member = CourseMember.objects.create(course=self.course, user=self.student, role=role, status=CourseMember.Status.REMOVED)
            with self.subTest(role=role), self.assertRaises(ValidationError):
                self.grant()
            member.refresh_from_db()
            self.assertEqual(member.role, role)
            member.delete()

    def test_revoke_never_modifies_other_course_membership(self):
        other_course = create_course(actor=self.other, title="Other Course")
        member = CourseMember.objects.create(course=other_course, user=self.student)
        with self.assertRaises(CourseMember.DoesNotExist):
            revoke_student_access(actor=self.teacher, course=self.course, member_id=member.pk)
        member.refresh_from_db()
        self.assertEqual(member.status, CourseMember.Status.ACTIVE)

    def test_existing_invited_and_suspended_students_can_be_activated(self):
        member = CourseMember.objects.create(course=self.course, user=self.student)
        for state in (CourseMember.Status.INVITED, CourseMember.Status.SUSPENDED):
            member.status = state
            member.save(update_fields=["status"])
            activated, created = self.grant()
            self.assertFalse(created)
            self.assertEqual(activated.status, CourseMember.Status.ACTIVE)
            self.assertEqual(activated.pk, member.pk)

    def test_member_listing_loads_profiles_in_one_query(self):
        self.grant()
        with self.assertNumQueries(1):
            data = CourseMemberSerializer(list_course_members(course=self.course), many=True).data
            self.assertEqual(len(data), 2)


class MemberAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("teacher", role=User.Role.TEACHER)
        cls.other = User.objects.create_user("other", role=User.Role.TEACHER)
        cls.student = User.objects.create_user("student")
        cls.student_two = User.objects.create_user("student_two")
        cls.admin = User.objects.create_superuser("admin")
        cls.course = create_course(actor=cls.teacher, title="Course")
        cls.other_course = create_course(actor=cls.other, title="Other Course")
        cls.outside_member = CourseMember.objects.create(course=cls.other_course, user=cls.student_two)

    def setUp(self):
        self.client = APIClient()
        self.members_url = reverse("courses:members", args=[self.course.pk])
        self.login_as(self.teacher)

    def login_as(self, user):
        authenticate_client(self.client, user)

    def grant(self, user=None, **extra):
        payload = {"user_id": str((user or self.student).pk), **extra}
        return self.client.post(self.members_url, payload, format="json")

    def revoke_url(self, member_id):
        return reverse("courses:member-revoke", args=[self.course.pk, member_id])

    def test_grant_list_revoke_repeat_and_regrant(self):
        response = self.grant()
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["role"], "STUDENT")
        self.assertEqual(data["user"]["id"], str(self.student.pk))
        self.assertEqual(data["course_id"], str(self.course.pk))
        self.assertNotIn("password", data["user"])
        repeated = self.grant()
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json(), data)
        listing = self.client.get(self.members_url)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["count"], 2)
        self.assertIn("no-store", listing["Cache-Control"])
        self.assertNotIn(str(self.outside_member.pk), [m["id"] for m in listing.json()["results"]])
        url = self.revoke_url(data["id"])
        self.assertEqual(self.client.delete(url).status_code, 204)
        member = CourseMember.objects.get(pk=data["id"])
        first_removal = member.removed_at
        self.assertEqual(member.status, CourseMember.Status.REMOVED)
        self.assertIsNotNone(first_removal)
        self.assertEqual(self.client.delete(url).status_code, 204)
        member.refresh_from_db()
        self.assertEqual(member.removed_at, first_removal)
        removed_list = self.client.get(self.members_url).json()
        self.assertEqual(removed_list["count"], 2)
        removed = next(m for m in removed_list["results"] if m["id"] == data["id"])
        self.assertEqual(removed["status"], "REMOVED")
        restored = self.grant()
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["id"], data["id"])
        self.assertEqual(restored.json()["joined_at"], data["joined_at"])
        self.assertIsNone(restored.json()["removed_at"])
        self.assertEqual(self.course.memberships.count(), 2)

    def test_grant_and_revoke_update_shared_view_permission_immediately(self):
        self.course = update_course(
            actor=self.teacher, course=self.course, changes={"status": Course.Status.PUBLISHED}
        )
        self.assertFalse(can_view_course(self.student, self.course))
        member_id = self.grant().json()["id"]
        self.assertTrue(can_view_course(self.student, self.course))
        self.assertEqual(self.client.delete(self.revoke_url(member_id)).status_code, 204)
        self.assertFalse(can_view_course(self.student, self.course))
        self.assertEqual(self.grant().status_code, 200)
        self.assertTrue(can_view_course(self.student, self.course))

    def test_list_is_paginated_and_scoped(self):
        for i in range(21):
            student = User.objects.create_user(f"student_{i}")
            CourseMember.objects.create(course=self.course, user=student)
        first = self.client.get(self.members_url).json()
        second = self.client.get(self.members_url, {"page": 2}).json()
        self.assertEqual(first["count"], 22)
        self.assertEqual(len(first["results"]), 20)
        self.assertEqual(len(second["results"]), 2)
        ids = [m["id"] for m in first["results"] + second["results"]]
        self.assertEqual(len(set(ids)), 22)
        self.assertNotIn(str(self.outside_member.pk), ids)

    def test_unrelated_teacher_student_and_admin_cannot_manage_members(self):
        member = CourseMember.objects.create(course=self.course, user=self.student)
        for user in (self.other, self.student, self.admin):
            with self.subTest(user=user):
                self.login_as(user)
                self.assertEqual(self.client.get(self.members_url).status_code, 403)
                self.assertEqual(self.grant(self.student_two).status_code, 403)
                self.assertEqual(self.client.delete(self.revoke_url(member.pk)).status_code, 403)
        member.refresh_from_db()
        self.assertEqual(member.status, CourseMember.Status.ACTIVE)

    def test_legacy_teacher_cannot_manage_members(self):
        member = CourseMember.objects.create(course=self.course, user=self.student)
        CourseMember.objects.create(course=self.course, user=self.other, role=CourseMember.Role.TEACHER, status=CourseMember.Status.REMOVED)
        self.login_as(self.other)
        self.assertEqual(self.client.get(self.members_url).status_code, 403)
        self.assertEqual(self.grant().status_code, 403)
        self.assertEqual(self.client.delete(self.revoke_url(member.pk)).status_code, 403)

    def test_non_active_manager_membership_is_denied(self):
        owner = self.course.memberships.get(user=self.teacher)
        for state in (CourseMember.Status.INVITED, CourseMember.Status.SUSPENDED, CourseMember.Status.REMOVED):
            owner.status = state
            owner.save(update_fields=["status"])
            self.assertEqual(self.client.get(self.members_url).status_code, 403)
            self.assertEqual(self.grant().status_code, 403)

    def test_blocked_logged_in_teacher_is_denied(self):
        self.teacher.status = User.Status.BLOCKED
        self.teacher.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.members_url).status_code, 401)
        self.assertEqual(self.grant().status_code, 401)

    def test_invalid_user_ids_accounts_and_extra_fields_are_rejected(self):
        blocked = User.objects.create_user("blocked", status=User.Status.BLOCKED)
        inactive = User.objects.create_user("inactive", status=User.Status.INACTIVE)
        for payload in ({}, {"user_id": None}, {"user_id": "invalid"}, {"user_id": str(uuid.uuid4())}):
            self.assertEqual(self.client.post(self.members_url, payload, format="json").status_code, 400)
        for user in (blocked, inactive, self.teacher, self.admin):
            self.assertEqual(self.grant(user).status_code, 400)
        self.assertEqual(self.grant(role="OWNER").status_code, 400)
        self.assertEqual(self.grant(status="ACTIVE").status_code, 400)
        self.assertEqual(self.course.memberships.count(), 1)

    def test_blocked_student_cannot_be_reactivated(self):
        response = self.grant()
        self.client.delete(self.revoke_url(response.json()["id"]))
        self.student.status = User.Status.BLOCKED
        self.student.save(update_fields=["status"])
        self.assertEqual(self.grant().status_code, 400)
        member = CourseMember.objects.get(pk=response.json()["id"])
        self.assertEqual(member.status, CourseMember.Status.REMOVED)

    def test_wrong_course_or_missing_member_is_not_found(self):
        for member_id in (self.outside_member.pk, uuid.uuid4()):
            self.assertEqual(self.client.delete(self.revoke_url(member_id)).status_code, 404)
        self.outside_member.refresh_from_db()
        self.assertEqual(self.outside_member.status, CourseMember.Status.ACTIVE)
        url = reverse("courses:members", args=[uuid.uuid4()])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"user_id": str(self.student.pk)}, format="json").status_code, 404)

    def test_owner_teacher_and_assistant_cannot_be_revoked(self):
        owner = self.course.memberships.get(user=self.teacher)
        self.assertEqual(self.client.delete(self.revoke_url(owner.pk)).status_code, 400)
        for role in (CourseMember.Role.TEACHER, CourseMember.Role.ASSISTANT):
            member = CourseMember.objects.create(course=self.course, user=self.other, role=role, status=CourseMember.Status.REMOVED)
            self.assertEqual(self.client.delete(self.revoke_url(member.pk)).status_code, 400)
            member.refresh_from_db()
            self.assertEqual(member.status, CourseMember.Status.REMOVED)
            member.delete()

    def test_jwt_and_method_restrictions(self):
        member = CourseMember.objects.create(course=self.course, user=self.student)
        url = self.revoke_url(member.pk)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.patch(self.members_url, {}, format="json").status_code, 405)
        self.client.credentials()
        self.assertEqual(self.grant().status_code, 401)
        self.assertEqual(self.client.delete(url).status_code, 401)
        self.assertEqual(self.client.get(self.members_url).status_code, 401)
        self.client = APIClient()
        self.assertEqual(self.client.get(self.members_url).status_code, 401)
        self.assertEqual(self.grant().status_code, 401)
        self.assertEqual(self.client.delete(url).status_code, 401)
