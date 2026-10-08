import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.enrollment_services import join_by_code, withdraw_classroom_enrollment
from apps.courses.models import Classroom, CourseMember, Enrollment, JoinRequest
from apps.courses.services import create_course, update_course
from apps.users.models import User
from common.testing import authenticate_client


class ClassroomManagementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("owner", role="TEACHER")
        self.other = User.objects.create_user("other", role="TEACHER")
        self.student = User.objects.create_user("student")
        self.second = User.objects.create_user("second")
        self.admin = User.objects.create_superuser("admin")
        self.course = create_course(actor=self.owner, title="Python")
        self.course = update_course(actor=self.owner, course=self.course, changes={"status": "PUBLISHED"})
        self.room = self.course.classrooms.get()
        self.second_room = Classroom.objects.create(course=self.course, name="Second class")
        self.enrollment = join_by_code(actor=self.student, class_code=self.room.class_code)[1]
        self.teacher = authenticate_client(APIClient(), self.owner)
        self.learner = authenticate_client(APIClient(), self.student)
        self.list_url = reverse("courses:classroom-enrollments", args=[self.course.pk, self.room.pk])
        self.own_url = reverse("courses:my-classrooms", args=[self.course.pk])

    def revoke_url(self, enrollment=None, room=None, course=None):
        return reverse("courses:classroom-enrollment-revoke", args=[
            (course or self.course).pk, (room or self.room).pk, (enrollment or self.enrollment).pk,
        ])

    def test_owner_roster_is_class_scoped_and_contains_public_student_information(self):
        join_by_code(actor=self.second, class_code=self.second_room.class_code)
        response = self.teacher.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        record = response.json()["results"][0]
        self.assertEqual(record["id"], str(self.enrollment.pk))
        self.assertEqual(record["classroom_id"], str(self.room.pk))
        self.assertEqual(record["student"]["id"], str(self.student.pk))
        self.assertNotIn("password", record["student"])
        self.assertNotIn("student_profile", record["student"])
        self.assertNotIn("class_code", record)

    def test_roster_status_filter_and_invalid_filter(self):
        self.enrollment.status = "COMPLETED"
        self.enrollment.completed_at = timezone.now()
        self.enrollment.save()
        self.assertEqual(self.teacher.get(self.list_url, {"status": "ACTIVE"}).json()["count"], 0)
        self.assertEqual(self.teacher.get(self.list_url, {"status": "COMPLETED"}).json()["count"], 1)
        self.assertEqual(self.teacher.get(self.list_url, {"status": "bad"}).status_code, 400)
        self.teacher.delete(self.revoke_url())
        self.assertEqual(self.teacher.get(self.list_url, {"status": "WITHDRAWN"}).json()["count"], 1)

    def test_roster_pagination(self):
        Enrollment.objects.bulk_create([
            Enrollment(classroom=self.room, student=User.objects.create_user(f"extra{i}").student_profile)
            for i in range(21)
        ])
        response = self.teacher.get(self.list_url)
        self.assertEqual(response.json()["count"], 22)
        self.assertEqual(len(response.json()["results"]), 20)
        self.assertEqual(len(self.teacher.get(self.list_url, {"page": 2}).json()["results"]), 2)
        self.assertEqual(self.teacher.get(self.list_url, {"page": 99}).status_code, 404)

    def test_only_owner_can_list_and_revoke(self):
        for user in (self.student, self.other, self.admin):
            client = authenticate_client(APIClient(), user)
            self.assertEqual(client.get(self.list_url).status_code, 403)
            self.assertEqual(client.delete(self.revoke_url()).status_code, 403)
        self.assertEqual(APIClient().get(self.list_url).status_code, 401)
        self.assertEqual(APIClient().delete(self.revoke_url()).status_code, 401)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, "ACTIVE")

    def test_class_and_enrollment_ids_must_match_course_and_each_other(self):
        foreign = create_course(actor=self.owner, title="Other course")
        foreign_room = foreign.classrooms.get()
        self.assertEqual(self.teacher.get(reverse("courses:classroom-enrollments", args=[self.course.pk, foreign_room.pk])).status_code, 404)
        self.assertEqual(self.teacher.delete(self.revoke_url(room=self.second_room)).status_code, 404)
        self.assertEqual(self.teacher.delete(self.revoke_url(course=foreign)).status_code, 404)
        missing = reverse("courses:classroom-enrollment-revoke", args=[self.course.pk, self.room.pk, uuid.uuid4()])
        self.assertEqual(self.teacher.delete(missing).status_code, 404)

    def test_withdraw_one_class_keeps_access_to_another(self):
        other = join_by_code(actor=self.student, class_code=self.second_room.class_code)[1]
        response = self.teacher.delete(self.revoke_url())
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.enrollment.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.enrollment.status, "WITHDRAWN")
        self.assertEqual(other.status, "ACTIVE")
        self.assertEqual(CourseMember.objects.get(user=self.student, course=self.course).status, "ACTIVE")
        self.assertEqual(self.learner.get(reverse("courses:update", args=[self.course.pk])).status_code, 200)
        own = self.learner.get(self.own_url).json()["results"]
        self.assertEqual([item["classroom_id"] for item in own], [str(self.second_room.pk)])

    def test_withdraw_last_class_removes_course_access_and_is_idempotent(self):
        self.assertEqual(self.teacher.delete(self.revoke_url()).status_code, 204)
        member = CourseMember.objects.get(course=self.course, user=self.student)
        removed_at = member.removed_at
        self.assertEqual(member.status, "REMOVED")
        self.assertIsNotNone(removed_at)
        self.assertEqual(self.teacher.delete(self.revoke_url()).status_code, 204)
        member.refresh_from_db()
        self.assertEqual(member.removed_at, removed_at)
        self.assertEqual(self.learner.get(self.own_url).status_code, 403)
        self.assertEqual(self.learner.get(reverse("courses:update", args=[self.course.pk])).status_code, 403)
        history = self.learner.get(reverse("courses:enrollments-mine")).json()["results"]
        self.assertEqual(history[0]["status"], "WITHDRAWN")

    def test_completed_class_retains_access_and_historical_values_survive_withdrawal(self):
        other = join_by_code(actor=self.student, class_code=self.second_room.class_code)[1]
        other.status = "COMPLETED"
        other.progress_percent = 100
        other.completed_at = timezone.now()
        other.save()
        self.teacher.delete(self.revoke_url())
        self.assertEqual(CourseMember.objects.get(user=self.student, course=self.course).status, "ACTIVE")
        self.teacher.delete(self.revoke_url(other, self.second_room))
        other.refresh_from_db()
        self.assertEqual(other.status, "WITHDRAWN")
        self.assertEqual(other.progress_percent, 100)
        self.assertIsNotNone(other.completed_at)

    def test_withdrawn_class_requires_new_approval_even_if_another_class_is_active(self):
        join_by_code(actor=self.student, class_code=self.second_room.class_code)
        self.teacher.delete(self.revoke_url())
        result, request, _ = join_by_code(actor=self.student, class_code=self.room.class_code)
        self.assertEqual(result, "PENDING")
        self.assertEqual(request.classroom_id, self.room.pk)
        self.assertEqual(Enrollment.objects.get(pk=self.enrollment.pk).status, "WITHDRAWN")

    def test_withdraw_does_not_restore_suspended_course_membership(self):
        join_by_code(actor=self.student, class_code=self.second_room.class_code)
        CourseMember.objects.filter(user=self.student, course=self.course).update(status="SUSPENDED")
        self.teacher.delete(self.revoke_url())
        self.assertEqual(CourseMember.objects.get(user=self.student, course=self.course).status, "SUSPENDED")

    def test_withdraw_does_not_affect_a_different_course(self):
        foreign = create_course(actor=self.owner, title="Other course")
        foreign = update_course(actor=self.owner, course=foreign, changes={"status": "PUBLISHED"})
        other = join_by_code(actor=self.student, class_code=foreign.classrooms.get().class_code)[1]
        self.teacher.delete(self.revoke_url())
        other.refresh_from_db()
        self.assertEqual(other.status, "ACTIVE")
        self.assertEqual(CourseMember.objects.get(user=self.student, course=foreign).status, "ACTIVE")

    def test_course_wide_revoke_still_withdraws_all_classes(self):
        join_by_code(actor=self.student, class_code=self.second_room.class_code)
        member = CourseMember.objects.get(course=self.course, user=self.student)
        self.assertEqual(self.teacher.delete(reverse("courses:member-revoke", args=[self.course.pk, member.pk])).status_code, 204)
        self.assertEqual(Enrollment.objects.filter(student__user=self.student, status="WITHDRAWN").count(), 2)

    def test_student_course_responses_show_only_own_effective_classes(self):
        join_by_code(actor=self.student, class_code=self.second_room.class_code)
        join_by_code(actor=self.second, class_code=self.room.class_code)
        detail = self.learner.get(reverse("courses:update", args=[self.course.pk])).json()
        listing = self.learner.get(reverse("courses:create")).json()["results"][0]
        self.assertEqual(len(detail["my_classrooms"]), 2)
        self.assertEqual(detail["my_classrooms"], listing["my_classrooms"])
        for item in detail["my_classrooms"]:
            self.assertNotIn("class_code", item)
            self.assertNotIn("student", item)
        teacher = self.teacher.get(reverse("courses:update", args=[self.course.pk])).json()
        self.assertEqual(teacher["my_classrooms"], [])

    def test_my_classrooms_requires_own_active_access_and_hides_other_students(self):
        join_by_code(actor=self.second, class_code=self.second_room.class_code)
        response = self.learner.get(self.own_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["classroom_id"], str(self.room.pk))
        self.assertEqual(self.teacher.get(self.own_url).status_code, 403)
        self.assertEqual(APIClient().get(self.own_url).status_code, 401)
        self.course.status = "ARCHIVED"
        self.course.save()
        self.assertEqual(self.learner.get(self.own_url).status_code, 403)

    def test_pending_applicant_has_no_classroom_access(self):
        policy = self.course.access_policy
        policy.require_approval = True
        policy.save()
        join_by_code(actor=self.second, class_code=self.room.class_code)
        client = authenticate_client(APIClient(), self.second)
        self.assertEqual(client.get(self.own_url).status_code, 403)
        self.assertTrue(JoinRequest.objects.filter(student=self.second, status="PENDING").exists())

    def test_service_checks_owner_and_rolls_back_when_membership_update_fails(self):
        with self.assertRaises(PermissionDenied):
            withdraw_classroom_enrollment(actor=self.other, course=self.course,
                                          classroom_id=self.room.pk, enrollment_id=self.enrollment.pk)
        with patch.object(CourseMember, "save", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                withdraw_classroom_enrollment(actor=self.owner, course=self.course,
                                              classroom_id=self.room.pk, enrollment_id=self.enrollment.pk)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, "ACTIVE")

    def test_classroom_list_serialization_has_bounded_queries(self):
        from apps.courses.api.serializers import CourseSerializer
        from apps.courses.selectors import list_accessible_courses
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        for i in range(4):
            extra = create_course(actor=self.owner, title=f"Course {i}")
            update_course(actor=self.owner, course=extra, changes={"status": "PUBLISHED"})
            join_by_code(actor=self.student, class_code=extra.classrooms.get().class_code)
        request = Request(APIRequestFactory().get("/"))
        request.user = self.student
        with self.assertNumQueries(3):
            data = CourseSerializer(list_accessible_courses(user=self.student), many=True, context={"request": request}).data
        self.assertEqual(len(data), 5)
