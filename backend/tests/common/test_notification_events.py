from django.test import TestCase
from apps.users.models import User
from apps.courses.services import create_course, update_course
from apps.courses.models import Classroom, ClassroomSession, CourseMember, Enrollment, ClassroomAnnouncement, AnnouncementComment
from apps.notifications.models import Notification
from apps.notifications.context import actor


class NotificationEventTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user('notification-owner', role='TEACHER')
        self.student = User.objects.create_user('notification-learner', role='STUDENT')
        self.outsider = User.objects.create_user('notification-outside', role='STUDENT')
        self.course = create_course(actor=self.teacher, title='Thông báo')
        update_course(actor=self.teacher, course=self.course, changes={'status': 'PUBLISHED'})
        self.room = Classroom.objects.create(course=self.course, name='Lớp')
        CourseMember.objects.create(course=self.course, user=self.student, role='STUDENT')
        Enrollment.objects.create(classroom=self.room, student=self.student.student_profile)
        Notification.objects.all().delete()

    def test_session_draft_noop_and_publication(self):
        token = actor.set(self.teacher)
        try:
            session = ClassroomSession.objects.create(classroom=self.room, is_draft=True)
            self.assertEqual(Notification.objects.count(), 0)
            session.is_draft = False; session.save()
            session.save()
            self.assertEqual(Notification.objects.filter(recipient=self.student, kind='SESSION_PUBLISHED').count(), 1)
            self.assertFalse(Notification.objects.filter(recipient=self.outsider).exists())
        finally:
            actor.reset(token)

    def test_reply_notifies_parent_and_owner_without_duplicate(self):
        post = ClassroomAnnouncement.objects.create(classroom=self.room, author=self.teacher, content='Bảng tin')
        parent = AnnouncementComment.objects.create(announcement=post, author=self.teacher, content='Xin chào')
        Notification.objects.all().delete()
        reply = AnnouncementComment.objects.create(announcement=post, author=self.student, parent=parent, content='Trả lời')
        self.assertEqual(Notification.objects.filter(recipient=self.teacher).count(), 1)
        item = Notification.objects.get()
        self.assertEqual(item.context['comment_id'], str(reply.pk))

    def test_revoked_access_redacts_history(self):
        ClassroomAnnouncement.objects.create(classroom=self.room, author=self.teacher, content='Nội dung bí mật')
        from rest_framework.test import APIClient
        client = APIClient(); client.force_authenticate(self.student)
        item = Notification.objects.filter(recipient=self.student).first()
        self.assertIsNotNone(item)
        self.assertEqual(client.get(f'/api/notifications/{item.pk}/target/').data['target']['classroom_name'], self.room.name)
        CourseMember.objects.filter(course=self.course, user=self.student).update(status='REMOVED')
        data = client.get('/api/notifications/').data['results'][0]
        self.assertEqual(data['title'], 'Hoạt động liên quan đến tài khoản của bạn')
        self.assertEqual(client.get(f'/api/notifications/{item.pk}/target/').status_code, 404)

    def test_video_publish_retry_revoke_and_republish(self):
        from apps.courses.video_models import SessionVideo
        session = ClassroomSession.objects.create(classroom=self.room, is_draft=False)
        Notification.objects.all().delete()
        video = SessionVideo.objects.create(session=session, title='Video', file='test.mp4', duration=10, content_type='video/mp4')
        self.assertFalse(Notification.objects.exists())
        video.is_published = True; video.save(); video.save()
        self.assertEqual(Notification.objects.filter(kind='VIDEO_PUBLISHED').count(), 1)
        video.is_published = False; video.save()
        video.is_published = True; video.save()
        self.assertEqual(Notification.objects.filter(kind='VIDEO_PUBLISHED').count(), 2)
        self.assertEqual(Notification.objects.filter(kind='VIDEO_WITHDRAWN').count(), 1)

    def test_submission_and_private_then_public_grade(self):
        import uuid
        from datetime import timedelta
        from django.utils import timezone
        from apps.courses.assessment_models import Assessment, AssessmentAttempt, AssessmentEvent
        from apps.courses.assessment_services import finalize
        session = ClassroomSession.objects.create(classroom=self.room, is_draft=False)
        assessment = Assessment.objects.create(session=session, title='Bài tập', kind='TEXT', mode='TEST', is_published=True, due_at=timezone.now()+timedelta(days=1))
        attempt = AssessmentAttempt.objects.create(assessment=assessment, student=self.student, request_id=uuid.uuid4(), number=1, expires_at=assessment.due_at)
        AssessmentEvent.objects.create(attempt=attempt, event_id=uuid.uuid4(), kind='TAB_HIDDEN')
        Notification.objects.all().delete()
        finalize(attempt); finalize(attempt)
        self.assertEqual(Notification.objects.filter(kind='ATTEMPT_SUBMITTED').count(), 1)
        self.assertEqual(Notification.objects.filter(kind='TEST_VIOLATIONS').count(), 1)
        attempt.score = 8; attempt.save()
        self.assertFalse(Notification.objects.filter(kind='GRADE_PUBLISHED').exists())
        attempt.grade_published = True; attempt.save(); attempt.save()
        self.assertEqual(Notification.objects.filter(kind='GRADE_PUBLISHED', recipient=self.student).count(), 1)

    def test_remove_classroom_notifies_before_enrollments_disappear(self):
        from apps.courses.enrollment_services import remove_classroom
        remove_classroom(actor=self.teacher, course=self.course, classroom_id=self.room.pk)
        self.assertEqual(Notification.objects.filter(kind='CLASSROOM_REMOVED', recipient=self.student).count(), 1)

    def test_join_approval_retry_and_mute_changes(self):
        from apps.courses.models import JoinRequest, ClassroomCommentMute
        from apps.courses.enrollment_services import review_request
        request = JoinRequest.objects.create(classroom=self.room, student=self.outsider)
        for _ in range(2):
            review_request(actor=self.teacher, course=self.course, request_id=request.pk, decision='approve')
        self.assertEqual(Notification.objects.filter(kind='JOIN_APPROVED', recipient=self.outsider).count(), 1)
        mute, _ = ClassroomCommentMute.objects.get_or_create(classroom=self.room, user=self.student, defaults={'muted_by': self.teacher})
        ClassroomCommentMute.objects.get_or_create(classroom=self.room, user=self.student, defaults={'muted_by': self.teacher})
        mute.delete()
        self.assertEqual(Notification.objects.filter(kind='COMMENT_MUTED', recipient=self.student).count(), 1)
        self.assertEqual(Notification.objects.filter(kind='COMMENT_UNMUTED', recipient=self.student).count(), 1)

    def test_bulk_results_publication_deduplicates_each_student(self):
        import uuid
        from datetime import timedelta
        from django.utils import timezone
        from apps.courses.assessment_models import Assessment, AssessmentAttempt
        session = ClassroomSession.objects.create(classroom=self.room, is_draft=False)
        assessment = Assessment.objects.create(session=session, title='Kết quả', kind='TEXT', mode='PRACTICE', is_published=True, due_at=timezone.now()+timedelta(days=1))
        for number in [1, 2]:
            AssessmentAttempt.objects.create(assessment=assessment, student=self.student, request_id=uuid.uuid4(), number=number, status='SUBMITTED', expires_at=assessment.due_at)
        Notification.objects.all().delete()
        assessment.results_published = True; assessment.save(); assessment.save()
        self.assertEqual(Notification.objects.filter(kind='RESULTS_PUBLISHED', recipient=self.student).count(), 1)

    def test_account_status_changes_remain_available_after_restore(self):
        self.student.status = 'BLOCKED'; self.student.is_active = False; self.student.save()
        self.student.status = 'ACTIVE'; self.student.is_active = True; self.student.save()
        self.assertEqual(Notification.objects.filter(kind='ACCOUNT_STATUS', recipient=self.student).count(), 2)

    def test_cascade_deletion_does_not_create_spurious_unmute(self):
        from apps.courses.models import ClassroomCommentMute
        ClassroomCommentMute.objects.create(classroom=self.room, user=self.student, muted_by=self.teacher)
        Notification.objects.all().delete()
        self.room.delete()
        self.assertFalse(Notification.objects.filter(kind='COMMENT_UNMUTED').exists())
