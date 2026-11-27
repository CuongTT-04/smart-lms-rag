from common.testing import approved_teacher
from datetime import timedelta
import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.assessment_models import Assessment, AssessmentAttempt
from apps.courses.enrollment_services import join_by_code, withdraw_classroom_enrollment
from apps.courses.models import Classroom, ClassroomSession, Enrollment
from apps.courses.services import create_course, update_course
from apps.courses.video_models import SessionVideo, VideoProgress
from apps.documents.models import DocumentVersion, KnowledgeDocument
from apps.users.models import User
from common.testing import authenticate_client


class ClassroomProgressAPITests(TestCase):
    def setUp(self):
        self.teacher = approved_teacher(User.objects.create_user('prog-teacher', role='TEACHER'))
        self.other_teacher = approved_teacher(User.objects.create_user('prog-other-teacher', role='TEACHER'))
        self.student = User.objects.create_user('prog-student', role='STUDENT')
        self.other_student = User.objects.create_user('prog-other-student', role='STUDENT')
        self.course = create_course(actor=self.teacher, title='Hệ điều hành')
        update_course(actor=self.teacher, course=self.course, changes={'status': 'PUBLISHED'})
        self.room = Classroom.objects.create(course=self.course, name='Lớp sáng')
        _, self.enrollment, _ = join_by_code(actor=self.student, class_code=self.room.class_code)
        self.session = ClassroomSession.objects.create(classroom=self.room, title='Buổi 1', is_draft=False)

        self.doc = KnowledgeDocument.objects.create(
            course=self.course, session=self.session, uploaded_by=self.teacher, title='Slide 1', is_published=True
        )
        self.v1 = DocumentVersion.objects.create(
            document=self.doc, version_number=1, file_name='s1.pdf', file_size_bytes=50,
            checksum_sha256='0' * 64, page_count=3, original_storage_key='s1.pdf', status='EXTRACTED',
        )
        self.doc.active_version = self.v1
        self.doc.published_version = self.v1
        self.doc.save(update_fields=['active_version', 'published_version'])

        self.video = SessionVideo.objects.create(
            session=self.session, title='Video 1', file='v1.mp4', content_type='video/mp4',
            duration=60, is_published=True,
        )
        self.quiz = Assessment.objects.create(
            session=self.session, title='Quiz 1', kind='QUIZ', mode='PRACTICE',
            questions=[{'id': 'q1', 'prompt': '?', 'choices': [{'id': 'a', 'text': 'A'}], 'correct_ids': ['a']}],
            due_at=timezone.now() + timedelta(days=2), is_published=True,
        )

        self.progress_url = f'/api/courses/{self.course.pk}/classrooms/{self.room.pk}/progress/'
        self.complete_url = f'{self.progress_url}documents/{self.v1.pk}/complete/'

        self.student_client = authenticate_client(APIClient(), self.student)
        self.teacher_client = authenticate_client(APIClient(), self.teacher)
        self.outsider_client = authenticate_client(APIClient(), self.other_student)

    def test_progress_get_and_mark_document_complete_permissions_and_validation(self):
        self.assertEqual(APIClient().get(self.progress_url).status_code, 401)
        self.assertEqual(APIClient().post(self.complete_url, {}, format='json').status_code, 401)

        self.assertEqual(self.outsider_client.get(self.progress_url).status_code, 404)
        self.assertEqual(self.outsider_client.post(self.complete_url, {}, format='json').status_code, 404)
        self.assertEqual(authenticate_client(APIClient(), self.other_teacher).get(self.progress_url).status_code, 404)

        self.assertEqual(self.teacher_client.get(self.progress_url).status_code, 403)
        self.assertEqual(self.teacher_client.post(self.complete_url, {}, format='json').status_code, 403)

        # Reject non-empty body attempts such as injecting student_id or percent.
        self.assertEqual(
            self.student_client.post(self.complete_url, {'student_id': str(self.other_student.pk)}, format='json').status_code,
            400,
        )
        self.assertEqual(
            self.student_client.post(self.complete_url, {'percent': 100}, format='json').status_code,
            400,
        )

        initial = self.student_client.get(self.progress_url)
        self.assertEqual(initial.status_code, 200)
        body = initial.json()
        self.assertEqual(body['total_activities'], 3)
        self.assertEqual(body['completed_activities'], 0)
        self.assertEqual(body['percent'], 0.0)
        self.assertTrue(body['has_activities'])
        self.assertIsNone(body['completed_at'])
        activities = body['sessions'][0]['activities']
        self.assertEqual([a['kind'] for a in activities], ['PDF', 'VIDEO', 'ASSESSMENT'])
        self.assertIn('version_id', activities[0])
        self.assertNotIn('version_id', activities[1])
        self.assertNotIn('version_id', activities[2])

        # Mark PDF complete twice -> idempotent 1/3 = 33.33%.
        marked = self.student_client.post(self.complete_url, {}, format='json')
        self.assertEqual(marked.status_code, 200)
        self.assertEqual(marked.json()['completed_activities'], 1)
        self.assertEqual(marked.json()['percent'], 33.33)
        self.assertTrue(marked.json()['sessions'][0]['activities'][0]['completed'])

        repeat = self.student_client.post(self.complete_url, {}, format='json')
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat.json()['completed_activities'], 1)

        # Missing / unpublished / draft / withdrawn resource returns 404.
        self.assertEqual(
            self.student_client.post(f'{self.progress_url}documents/{uuid.uuid4()}/complete/', {}, format='json').status_code,
            404,
        )

        # Completing video and submitting quiz completes the classroom.
        VideoProgress.objects.create(video=self.video, student=self.student, position=60, watched_until=60, completed_at=timezone.now())
        AssessmentAttempt.objects.create(
            assessment=self.quiz, student=self.student, request_id=uuid.uuid4(), number=1,
            status='SUBMITTED', submitted_at=timezone.now(), score=10,
            expires_at=timezone.now() + timedelta(days=1),
        )
        done = self.student_client.get(self.progress_url)
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.json()['completed_activities'], 3)
        self.assertEqual(done.json()['percent'], 100.0)

        # Withdrawn student is blocked with 404.
        withdraw_classroom_enrollment(
            actor=self.teacher, course=self.course, classroom_id=self.room.pk, enrollment_id=self.enrollment.pk
        )
        self.assertEqual(self.student_client.get(self.progress_url).status_code, 404)
        self.assertEqual(self.student_client.post(self.complete_url, {}, format='json').status_code, 404)
