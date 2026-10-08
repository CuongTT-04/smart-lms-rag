import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.courses.api.serializers import CourseSerializer
from apps.courses.models import Course, CourseMember
from apps.courses.permissions import can_view_course
from apps.courses.selectors import list_accessible_courses
from apps.courses.services import create_course, update_course
from common.testing import authenticate_client


User = get_user_model()


class CourseSelectorTests(TestCase):
    def test_list_and_detail_permissions_agree_across_roles_and_states(self):
        user = User.objects.create_user("user")
        course = Course.objects.create(title="Policy Course")
        member = CourseMember.objects.create(course=course, user=user)
        for user_role in User.Role.values:
            user.role = user_role
            user.save(update_fields=["role"])
            for course_status in Course.Status.values:
                course.status = course_status
                Course.objects.filter(pk=course.pk).update(status=course_status)
                for member_role in CourseMember.Role.values:
                    for member_status in CourseMember.Status.values:
                        if member_role in (CourseMember.Role.TEACHER, CourseMember.Role.ASSISTANT) and member_status != CourseMember.Status.REMOVED:
                            continue
                        with self.subTest(
                            user_role=user_role, course_status=course_status,
                            member_role=member_role, member_status=member_status,
                        ):
                            CourseMember.objects.filter(pk=member.pk).update(
                                role=member_role, status=member_status
                            )
                            listed = list_accessible_courses(user=user).filter(pk=course.pk).exists()
                            self.assertEqual(listed, can_view_course(user, course))

    def test_anonymous_and_disabled_accounts_have_no_accessible_courses(self):
        user = User.objects.create_user("teacher", role=User.Role.TEACHER)
        course = create_course(actor=user, title="Course")
        self.assertFalse(list_accessible_courses(user=AnonymousUser()).exists())
        user.status = User.Status.BLOCKED
        user.save(update_fields=["status"])
        self.assertFalse(list_accessible_courses(user=user).exists())
        self.assertFalse(can_view_course(user, course))

    def test_serializing_courses_does_not_query_membership_per_item(self):
        teacher = User.objects.create_user("teacher", role=User.Role.TEACHER)
        for i in range(3):
            create_course(actor=teacher, title=f"Course {i}")
        with self.assertNumQueries(1):
            data = CourseSerializer(list_accessible_courses(user=teacher), many=True).data
            self.assertEqual(len(data), 3)


class CourseAccessAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("teacher", role=User.Role.TEACHER)
        cls.other_teacher = User.objects.create_user("other_teacher", role=User.Role.TEACHER)
        cls.student = User.objects.create_user("student")
        cls.other_student = User.objects.create_user("other_student")
        cls.admin = User.objects.create_superuser("admin")

        cls.draft = create_course(actor=cls.teacher, title="Draft")
        cls.published = create_course(actor=cls.teacher, title="Published")
        cls.published = update_course(
            actor=cls.teacher, course=cls.published, changes={"status": Course.Status.PUBLISHED}
        )
        cls.archived = create_course(actor=cls.teacher, title="Archived")
        cls.archived = update_course(
            actor=cls.teacher, course=cls.archived, changes={"status": Course.Status.ARCHIVED}
        )
        cls.outside = create_course(actor=cls.other_teacher, title="Outside")
        cls.outside = update_course(
            actor=cls.other_teacher, course=cls.outside, changes={"status": Course.Status.PUBLISHED}
        )
        cls.co_taught = create_course(actor=cls.other_teacher, title="Co-taught")
        CourseMember.objects.create(
            course=cls.co_taught, user=cls.teacher, role=CourseMember.Role.TEACHER, status=CourseMember.Status.REMOVED
        )
        CourseMember.objects.create(course=cls.outside, user=cls.admin, role=CourseMember.Role.STUDENT)
        for course in (cls.draft, cls.published, cls.archived):
            CourseMember.objects.create(course=course, user=cls.student)
        CourseMember.objects.create(course=cls.outside, user=cls.other_student)

    def setUp(self):
        self.list_url = reverse("courses:create")
        self.client = self.authenticated_client(self.student)

    def authenticated_client(self, user):
        return authenticate_client(APIClient(), user)

    def detail_url(self, course):
        return reverse("courses:update", args=[course.pk])

    def listed_ids(self, client=None):
        response = (client or self.client).get(self.list_url)
        self.assertEqual(response.status_code, 200)
        return {course["id"] for course in response.json()["results"]}

    def test_teacher_lists_and_views_only_owned_courses_in_all_states(self):
        self.client = self.authenticated_client(self.teacher)
        expected = (self.draft, self.published, self.archived)
        self.assertEqual(self.listed_ids(), {str(course.pk) for course in expected})
        for course in expected:
            self.assertEqual(self.client.get(self.detail_url(course)).status_code, 200)
        self.assertEqual(self.client.get(self.detail_url(self.outside)).status_code, 403)
        self.assertEqual(self.client.get(self.detail_url(self.co_taught)).status_code, 403)

    def test_student_only_lists_and_views_granted_published_courses(self):
        self.assertEqual(self.listed_ids(), {str(self.published.pk)})
        response = self.client.get(self.detail_url(self.published))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.published.pk))
        self.assertEqual(
            set(response.json()),
            {"id", "title", "description", "status", "created_at", "updated_at", "published_at", "my_classrooms"},
        )
        self.assertEqual(response.json()["my_classrooms"], [])
        for course in (self.draft, self.archived, self.outside, self.co_taught):
            denied = self.client.get(self.detail_url(course))
            self.assertEqual(denied.status_code, 403)
            self.assertNotIn("title", denied.json())

    def test_admin_flags_and_membership_do_not_bypass_business_role(self):
        self.client = self.authenticated_client(self.admin)
        self.assertEqual(self.listed_ids(), set())
        self.assertEqual(self.client.get(self.detail_url(self.outside)).status_code, 403)

    def test_list_scope_cannot_be_overridden_by_query_parameters(self):
        response = self.client.get(
            self.list_url, {"user_id": str(self.other_teacher.pk), "role": "TEACHER", "status": "DRAFT"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {course["id"] for course in response.json()["results"]}, {str(self.published.pk)}
        )

    def test_no_memberships_returns_empty_paginated_list(self):
        user = User.objects.create_user("new_student")
        self.client = self.authenticated_client(user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"count": 0, "next": None, "previous": None, "results": []})

    def test_pagination_only_counts_visible_courses_and_has_no_duplicates(self):
        added = [create_course(actor=self.teacher, title=f"Course {i}") for i in range(21)]
        self.client = self.authenticated_client(self.teacher)
        first = self.client.get(self.list_url).json()
        second = self.client.get(self.list_url, {"page": 2}).json()
        self.assertEqual(first["count"], 24)
        self.assertEqual(len(first["results"]), 20)
        self.assertEqual(len(second["results"]), 4)
        actual = [course["id"] for course in first["results"] + second["results"]]
        expected = {str(course.pk) for course in added + [self.draft, self.published, self.archived]}
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual(set(actual), expected)

    def test_suspended_and_removed_memberships_are_hidden(self):
        member = self.published.memberships.get(user=self.student)
        for state in (CourseMember.Status.SUSPENDED, CourseMember.Status.REMOVED):
            member.status = state
            member.save(update_fields=["status"])
            self.assertEqual(self.listed_ids(), set())
            self.assertEqual(self.client.get(self.detail_url(self.published)).status_code, 403)

    def test_revoke_and_restore_affect_next_request_without_logging_student_out(self):
        teacher_client = self.authenticated_client(self.teacher)
        member = self.published.memberships.get(user=self.student)
        self.assertEqual(self.client.get(self.detail_url(self.published)).status_code, 200)
        url = reverse("courses:member-revoke", args=[self.published.pk, member.pk])
        self.assertEqual(teacher_client.delete(url).status_code, 204)
        self.assertEqual(self.listed_ids(), set())
        self.assertEqual(self.client.get(self.detail_url(self.published)).status_code, 403)
        self.assertEqual(self.client.get(reverse("users:me")).status_code, 200)
        classroom = self.published.classrooms.get()
        pending = self.client.post(reverse("courses:join"), {"class_code": classroom.class_code}, format="json")
        request_id = pending.json()["join_request"]["id"]
        url = reverse("courses:request-review", args=[self.published.pk, request_id])
        restored = teacher_client.post(url, {"decision": "approve"}, format="json")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["status"], "APPROVED")
        self.assertEqual(self.listed_ids(), {str(self.published.pk)})
        self.assertEqual(self.client.get(self.detail_url(self.published)).status_code, 200)

    def test_archiving_hides_course_from_student_but_preserves_teacher_access(self):
        teacher_client = self.authenticated_client(self.teacher)
        detail = self.detail_url(self.published)
        self.assertEqual(teacher_client.patch(detail, {"status": "ARCHIVED"}, format="json").status_code, 200)
        self.assertEqual(self.listed_ids(), set())
        self.assertEqual(self.client.get(detail).status_code, 403)
        self.assertEqual(teacher_client.get(detail).status_code, 200)
        self.assertEqual(self.published.memberships.count(), 2)
        self.assertEqual(teacher_client.patch(detail, {"status": "PUBLISHED"}, format="json").status_code, 200)
        self.assertEqual(self.client.get(detail).status_code, 200)

    def test_removed_teacher_and_blocked_account_lose_read_access(self):
        teacher_client = self.authenticated_client(self.teacher)
        owner = self.draft.memberships.get(user=self.teacher)
        owner.status = CourseMember.Status.REMOVED
        owner.save(update_fields=["status"])
        self.assertNotIn(str(self.draft.pk), self.listed_ids(teacher_client))
        self.assertEqual(teacher_client.get(self.detail_url(self.draft)).status_code, 403)
        self.student.status = User.Status.BLOCKED
        self.student.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.list_url).status_code, 401)
        self.assertEqual(self.client.get(self.detail_url(self.published)).status_code, 401)

    def test_role_change_does_not_inherit_access_from_mismatched_membership(self):
        self.student.role = User.Role.TEACHER
        self.student.save(update_fields=["role"])
        self.assertEqual(self.listed_ids(), set())
        self.assertEqual(self.client.get(self.detail_url(self.published)).status_code, 403)
        teacher_client = self.authenticated_client(self.teacher)
        self.teacher.role = User.Role.STUDENT
        self.teacher.save(update_fields=["role"])
        self.assertEqual(self.listed_ids(teacher_client), set())
        self.assertEqual(teacher_client.get(self.detail_url(self.published)).status_code, 403)

    def test_read_access_does_not_grant_write_or_member_management(self):
        detail = self.detail_url(self.published)
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.patch(detail, {"title": "Forbidden"}, format="json").status_code, 403)
        self.assertEqual(self.client.post(self.list_url, {"title": "Forbidden"}, format="json").status_code, 403)
        url = reverse("courses:members", args=[self.published.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.published.refresh_from_db()
        self.assertEqual(self.published.title, "Published")

    def test_jwt_unknown_ids_and_cache_control(self):
        response = self.client.get(self.list_url)
        self.assertIn("no-store", response["Cache-Control"])
        response = self.client.get(self.detail_url(self.published))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.head(self.detail_url(self.published)).status_code, 200)
        unknown = reverse("courses:update", args=[uuid.uuid4()])
        self.assertEqual(self.client.get(unknown).status_code, 404)
        self.assertEqual(self.client.get("/api/courses/not-a-uuid/").status_code, 404)
        anonymous = APIClient()
        self.assertEqual(anonymous.get(self.list_url).status_code, 401)
        self.assertEqual(anonymous.get(self.detail_url(self.published)).status_code, 401)
