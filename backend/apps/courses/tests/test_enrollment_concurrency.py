from apps.courses.models import Classroom
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.courses.enrollment_services import join_by_code, review_request, withdraw_classroom_enrollment
from apps.courses.models import Classroom, CourseMember, Enrollment, JoinRequest
from apps.courses.services import create_course, update_course
from apps.users.models import User


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class EnrollmentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("concurrent_owner", role="TEACHER")
        self.student = User.objects.create_user("concurrent_student")
        self.course = create_course(actor=self.owner, title="Concurrent")
        self.course = update_course(actor=self.owner, course=self.course, changes={"status": "PUBLISHED"})
        self.code = Classroom.objects.create(course=self.course, name=self.course.title).class_code

    def concurrent(self, callback, second_callback=None):
        barrier = Barrier(2)

        def worker(action):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return action()
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, action) for action in (callback, second_callback or callback)]
            return [future.result(timeout=20) for future in futures]

    def test_simultaneous_direct_joins_create_one_membership_and_enrollment(self):
        results = self.concurrent(lambda: join_by_code(actor=self.student, class_code=self.code))
        self.assertEqual(sorted(result[2] for result in results), [False, True])
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(CourseMember.objects.filter(user=self.student).count(), 1)

    def test_simultaneous_withdrawals_from_two_classes_remove_last_access(self):
        first = join_by_code(actor=self.student, class_code=self.code)[1]
        room = Classroom.objects.create(course=self.course, name="Second class")
        second = join_by_code(actor=self.student, class_code=room.class_code)[1]
        self.concurrent(
            lambda: withdraw_classroom_enrollment(actor=self.owner, course=self.course,
                                                 classroom_id=first.classroom_id, enrollment_id=first.pk),
            lambda: withdraw_classroom_enrollment(actor=self.owner, course=self.course,
                                                 classroom_id=second.classroom_id, enrollment_id=second.pk),
        )
        self.assertEqual(Enrollment.objects.filter(status="WITHDRAWN").count(), 2)
        self.assertEqual(CourseMember.objects.get(user=self.student).status, "REMOVED")

    def test_concurrent_approval_and_withdrawal_keep_access_consistent(self):
        enrollment = join_by_code(actor=self.student, class_code=self.code)[1]
        withdraw_classroom_enrollment(actor=self.owner, course=self.course,
                                     classroom_id=enrollment.classroom_id, enrollment_id=enrollment.pk)
        request = join_by_code(actor=self.student, class_code=self.code)[1]
        self.concurrent(
            lambda: review_request(actor=self.owner, course=self.course, request_id=request.pk, decision="approve"),
            lambda: withdraw_classroom_enrollment(actor=self.owner, course=self.course,
                                                 classroom_id=enrollment.classroom_id, enrollment_id=enrollment.pk),
        )
        enrollment.refresh_from_db()
        member = CourseMember.objects.get(user=self.student)
        self.assertEqual(member.status, "ACTIVE" if enrollment.status == "ACTIVE" else "REMOVED")
        self.assertEqual(CourseMember.objects.filter(user=self.student).count(), 1)

    def test_simultaneous_requests_and_approvals_are_idempotent(self):
        Classroom.objects.filter(course=self.course).update(require_approval=True)
        self.concurrent(lambda: join_by_code(actor=self.student, class_code=self.code))
        request = JoinRequest.objects.get()
        self.concurrent(lambda: review_request(actor=self.owner, course=self.course, request_id=request.pk, decision="approve"))
        request.refresh_from_db()
        self.assertEqual(request.status, "APPROVED")
        self.assertEqual(Enrollment.objects.count(), 1)
