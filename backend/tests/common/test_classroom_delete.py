from django.test import TestCase
from rest_framework.test import APIClient
from apps.users.models import User
from apps.courses.models import Classroom, ClassroomSession, Enrollment, JoinRequest
from apps.documents.models import KnowledgeDocument, DocumentVersion, IngestionJob
from apps.courses.services import create_course
from common.testing import authenticate_client


class ClassroomDeleteTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('delete-class-owner', role='TEACHER')
        self.course = create_course(actor=self.owner, title='Course')
        self.room = Classroom.objects.create(course=self.course, name='Delete me')
        self.client = authenticate_client(APIClient(), self.owner)
        self.url = f'/api/courses/{self.course.pk}/classrooms/{self.room.pk}/'

    def test_new_course_does_not_create_a_classroom(self):
        new_course = create_course(actor=self.owner, title='Empty course')
        self.assertFalse(new_course.classrooms.exists())

    def test_delete_hides_class_and_sessions_and_closes_joining(self):
        session = ClassroomSession.objects.create(classroom=self.room, title='Session')
        student = User.objects.create_user('delete-class-student', role='STUDENT')
        request = JoinRequest.objects.create(classroom=self.room, student=student)
        enrollment = Enrollment.objects.create(classroom=self.room, student=student.student_profile)
        other_room = Classroom.objects.create(course=self.course, name='Keep me')
        document = KnowledgeDocument.objects.create(course=self.course, session=session, uploaded_by=self.owner, title='PDF')
        common_document = KnowledgeDocument.objects.create(course=self.course, uploaded_by=self.owner, title='Shared PDF')
        version = DocumentVersion.objects.create(document=document, version_number=1, file_name='test.pdf', file_size_bytes=1, checksum_sha256='0'*64, page_count=1, original_storage_key='test.pdf')
        job = IngestionJob.objects.create(document_version=version, idempotency_key='delete-room-job', payload_digest='0'*64)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204, response.content)
        self.room.refresh_from_db(); session.refresh_from_db(); request.refresh_from_db()
        self.assertIsNotNone(self.room.removed_at)
        self.assertIsNotNone(session.removed_at)
        self.assertEqual(request.status, 'CANCELED')
        enrollment.refresh_from_db()
        document.refresh_from_db()
        version.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(enrollment.status, 'WITHDRAWN')
        self.assertIsNotNone(document.removed_at)
        self.assertEqual(version.status, 'REMOVED')
        self.assertEqual(job.status, 'CANCELLED')
        self.assertTrue(Classroom.objects.filter(pk=other_room.pk).exists())
        common_document.refresh_from_db()
        self.assertIsNone(common_document.removed_at)
        self.assertEqual(self.client.get(f'/api/documents/{document.pk}/status/').status_code, 404)
        self.assertFalse(Classroom.objects.filter(pk=self.room.pk).exists())
        self.assertEqual(self.client.patch(self.url, {'name': 'Restored'}, format='json').status_code, 404)
        self.assertEqual(self.client.get(self.url + 'sessions/').status_code, 404)
        student_client = authenticate_client(APIClient(), student)
        self.assertEqual(student_client.post('/api/courses/join/', {'class_code': self.room.class_code}, format='json').status_code, 400)

    def test_other_owner_cannot_delete_class(self):
        other = User.objects.create_user('delete-class-other', role='TEACHER')
        response = authenticate_client(APIClient(), other).delete(self.url)
        self.assertIn(response.status_code, [403, 404])
        self.assertTrue(Classroom.objects.filter(pk=self.room.pk).exists())
