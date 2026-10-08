from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


NEW_MIGRATION = "0003_accesspolicy_classroom_enrollment_joinrequest_and_more"


class EnrollmentMigrationTests(TransactionTestCase):
    def test_existing_memberships_are_preserved_and_invitations_retired(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("courses", "0002_single_course_owner")])
        old = executor.loader.project_state([("courses", "0002_single_course_owner")]).apps
        try:
            User = old.get_model("users", "User")
            Course = old.get_model("courses", "Course")
            Member = old.get_model("courses", "CourseMember")
            course = Course.objects.create(title="Existing")
            student = User.objects.create(username="existing_student", role="STUDENT")
            invited = User.objects.create(username="existing_invited", role="STUDENT")
            active = Member.objects.create(course=course, user=student, status="ACTIVE")
            invite = Member.objects.create(course=course, user=invited, status="INVITED")
            executor = MigrationExecutor(connection)
            executor.migrate([("courses", NEW_MIGRATION)])
            state = executor.loader.project_state([("courses", NEW_MIGRATION)]).apps
            Classroom = state.get_model("courses", "Classroom")
            Enrollment = state.get_model("courses", "Enrollment")
            Member = state.get_model("courses", "CourseMember")
            Policy = state.get_model("courses", "AccessPolicy")
            classroom = Classroom.objects.get(course_id=course.pk)
            self.assertEqual(len(classroom.class_code), 12)
            self.assertEqual(Policy.objects.get(course_id=course.pk).access_type, "FREE")
            self.assertEqual(Member.objects.get(pk=active.pk).status, "ACTIVE")
            retired = Member.objects.get(pk=invite.pk)
            self.assertEqual(retired.status, "REMOVED")
            self.assertIsNotNone(retired.removed_at)
            enrolled = Enrollment.objects.get(classroom=classroom, student__user_id=student.pk)
            self.assertEqual(enrolled.status, "ACTIVE")
            self.assertEqual(enrolled.enrolled_at, active.joined_at)
            self.assertEqual(Enrollment.objects.get(student__user_id=invited.pk).status, "WITHDRAWN")
        finally:
            MigrationExecutor(connection).migrate([("courses", NEW_MIGRATION)])
