from apps.courses.models import Classroom
from django.test import TestCase
from rest_framework.test import APIClient
from apps.courses.services import create_course, update_course
from apps.users.models import User
from common.testing import authenticate_client

class ClassroomSessionTests(TestCase):
    def test_delete_session_hides_session_and_materials_but_retains_records(self):
        from apps.courses.models import ClassroomSession
        from apps.documents.models import KnowledgeDocument, DocumentVersion
        session=ClassroomSession.objects.create(classroom=self.room,title='Delete me')
        document=KnowledgeDocument.objects.create(course=self.course,session=session,uploaded_by=self.owner,title='PDF')
        version=DocumentVersion.objects.create(document=document,version_number=1,file_name='test.pdf',file_size_bytes=1,checksum_sha256='0'*64,page_count=1,original_storage_key='test.pdf',status='QUEUED')
        url=self.url+str(session.pk)+'/'
        other=authenticate_client(APIClient(),self.other)
        self.assertEqual(other.delete(url).status_code,404)
        self.assertEqual(self.client.delete(url).status_code,204)
        session.refresh_from_db();document.refresh_from_db();version.refresh_from_db()
        self.assertIsNotNone(session.removed_at)
        self.assertIsNotNone(document.removed_at)
        self.assertEqual(version.status,'REMOVED')
        self.assertEqual(self.client.get(self.url).json()['results'],[])
        self.assertEqual(self.client.patch(url,{'title':'No'},format='json').status_code,404)
        self.assertEqual(self.client.get(f'/api/documents/{document.pk}/status/').status_code,404)
        self.assertEqual(self.client.get(f'/api/courses/{self.course.pk}/documents/?session_id={session.pk}').status_code,404)
    def test_draft_session_can_be_finalized_only_by_owner_and_survives_reload(self):
        session = self.client.post(self.url, {}, format='json').json()
        self.assertIs(session.get('is_draft'), True)
        url = self.url + session['id'] + '/'
        other = authenticate_client(APIClient(), self.other)
        self.assertEqual(other.patch(url, {'is_draft': False}, format='json').status_code, 404)
        self.assertEqual(self.client.patch(url, {'is_draft': True}, format='json').status_code, 400)
        response = self.client.patch(url, {'is_draft': False}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()['is_draft'], False)
        self.assertIs(self.client.get(self.url).json()['results'][0]['is_draft'], False)
        self.assertEqual(self.client.patch(url, {'is_draft': False}, format='json').status_code, 200)
        self.assertEqual(self.client.post(self.url, {'is_draft': False}, format='json').status_code, 400)
    def setUp(self):
        self.owner=User.objects.create_user('session-owner',role='TEACHER')
        self.other=User.objects.create_user('session-other',role='TEACHER')
        self.student=User.objects.create_user('session-student')
        self.course=create_course(actor=self.owner,title='Python')
        update_course(actor=self.owner,course=self.course,changes={'status':'PUBLISHED'})
        self.room=Classroom.objects.create(course=self.course, name=self.course.title)
        self.url=f'/api/courses/{self.course.pk}/classrooms/{self.room.pk}/sessions/'
        self.client=authenticate_client(APIClient(),self.owner)

    def test_owner_creates_persisted_session_and_other_teacher_cannot_read(self):
        result=self.client.post(self.url,{'title':'Buổi 1'},format='json')
        self.assertEqual(result.status_code,201,result.content)
        self.assertEqual(self.client.get(self.url).json()['results'][0]['title'],'Buổi 1')
        other=authenticate_client(APIClient(),self.other)
        self.assertIn(other.get(self.url).status_code,[403,404])

    def test_unenrolled_student_cannot_read_or_create_sessions(self):
        student=authenticate_client(APIClient(),self.student)
        self.assertIn(student.get(self.url).status_code,[403,404])
        self.assertIn(student.post(self.url,{'title':'Forbidden'},format='json').status_code,[403,404])

    def test_private_materials_require_enrollment_in_their_classroom(self):
        from apps.courses.models import Classroom, ClassroomSession
        from apps.courses.enrollment_services import join_by_code
        from apps.documents.models import KnowledgeDocument, DocumentVersion
        other_room=Classroom.objects.create(course=self.course,name='Other room')
        sessions=[ClassroomSession.objects.create(classroom=room,title='Lesson') for room in [self.room,other_room]]
        documents=[]
        for session in sessions:
            document=KnowledgeDocument.objects.create(course=self.course,session=session,uploaded_by=self.owner,title='Material',is_published=True)
            version=DocumentVersion.objects.create(document=document,version_number=1,file_name='test.pdf',file_size_bytes=1,checksum_sha256='0'*64,page_count=1,original_storage_key='test.pdf',status='EXTRACTED')
            document.published_version=version;document.save()
            documents.append(document)
        join_by_code(actor=self.student,class_code=self.room.class_code)
        student=authenticate_client(APIClient(),self.student)
        self.assertEqual(student.get(self.url).status_code,200)
        self.assertEqual(student.get(f'/api/courses/{self.course.pk}/classrooms/{other_room.pk}/sessions/').status_code,404)
        self.assertEqual(student.get(f'/api/documents/{documents[0].pk}/status/').status_code,200)
        self.assertEqual(student.get(f'/api/documents/{documents[1].pk}/status/').status_code,404)
        self.assertEqual(student.get(f'/api/documents/{documents[1].pk}/view/').status_code,404)
        self.assertEqual(student.get(f'/api/documents/{documents[1].pk}/download/').status_code,404)
        listed=student.get(f'/api/courses/{self.course.pk}/documents/').json()['results']
        self.assertEqual([item['document_id'] for item in listed],[str(documents[0].pk)])
        self.assertEqual(student.get(f'/api/courses/{self.course.pk}/documents/?session_id={sessions[1].pk}').status_code,404)

    def test_upload_rejects_a_session_from_a_different_course(self):
        from apps.courses.models import ClassroomSession
        other_course=create_course(actor=self.owner,title='Other course')
        session=ClassroomSession.objects.create(classroom=Classroom.objects.create(course=other_course, name=other_course.title),title='Other lesson')
        result=self.client.post(f'/api/courses/{self.course.pk}/documents/',{'session_id':str(session.pk)},format='multipart',HTTP_IDEMPOTENCY_KEY='other-scope')
        self.assertEqual(result.status_code,404)

    def test_owner_can_create_blank_session(self):
        result = self.client.post(self.url, {}, format='json')
        self.assertEqual(result.status_code, 201, result.content)
        self.assertEqual(result.json()['title'], '')

    def test_announcements_are_persisted_and_class_scoped(self):
        from apps.courses.enrollment_services import join_by_code
        url = self.url.replace('sessions/', 'announcements/')
        result = self.client.post(url, {'content': 'Thông báo buổi học'}, format='json')
        self.assertEqual(result.status_code, 201, result.content)
        self.assertEqual(self.client.get(url).json()['results'][0]['content'], 'Thông báo buổi học')
        student = authenticate_client(APIClient(), self.student)
        self.assertEqual(student.get(url).status_code, 404)
        join_by_code(actor=self.student, class_code=self.room.class_code)
        self.assertEqual(student.get(url).status_code, 200)
        self.assertEqual(student.post(url, {'content': 'No'}, format='json').status_code, 404)
        other = authenticate_client(APIClient(), self.other)
        self.assertEqual(other.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'content': '   '}, format='json').status_code, 400)

    def test_announcement_image_and_link_are_private_and_validated(self):
        import io, tempfile
        from PIL import Image
        from django.test import override_settings
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.courses.enrollment_services import join_by_code
        url = self.url.replace('sessions/', 'announcements/')
        with tempfile.TemporaryDirectory() as root, override_settings(ANNOUNCEMENTS_STORAGE_ROOT=root):
            stream = io.BytesIO()
            Image.new('RGB', (10, 10), 'green').save(stream, format='PNG')
            result = self.client.post(url, {'content': 'Ảnh buổi học', 'link': 'https://example.com/lesson', 'image': SimpleUploadedFile('lesson.png', stream.getvalue(), 'image/png')}, format='multipart')
            self.assertEqual(result.status_code, 201, result.content)
            self.assertTrue(result.json()['has_image'])
            self.assertEqual(result.json()['link'], 'https://example.com/lesson')
            image_url = url + result.json()['id'] + '/image/'
            image = self.client.get(image_url)
            self.assertEqual(image.status_code, 200)
            self.assertEqual(self.client.post(image_url, {}, format='json').status_code, 405)
            self.assertEqual(image['Content-Type'], 'image/png')
            image.close()
            student = authenticate_client(APIClient(), self.student)
            self.assertEqual(student.get(image_url).status_code, 404)
            join_by_code(actor=self.student, class_code=self.room.class_code)
            allowed = student.get(image_url)
            self.assertEqual(allowed.status_code, 200)
            allowed.close()
            self.assertEqual(APIClient().get(image_url).status_code, 401)
            invalid = self.client.post(url, {'content': 'No', 'image': SimpleUploadedFile('fake.png', b'not an image', 'image/png')}, format='multipart')
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(self.client.post(url, {'content': 'No', 'link': 'javascript:alert(1)'}, format='json').status_code, 400)

    def test_only_owner_can_rename_session(self):
        session = self.client.post(self.url, {}, format='json').json()
        url = self.url + session['id'] + '/'
        result = self.client.patch(url, {'title': 'Ngày 1'}, format='json')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(self.client.get(self.url).json()['results'][0]['title'], 'Ngày 1')
        other = authenticate_client(APIClient(), self.other)
        self.assertEqual(other.patch(url, {'title': 'No'}, format='json').status_code, 404)
