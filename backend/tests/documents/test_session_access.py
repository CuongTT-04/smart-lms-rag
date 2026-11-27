"""Session visibility is enforced by APIs/media and the retrieval boundary."""
from common.testing import approved_teacher
import hashlib
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Classroom, Enrollment
from apps.documents.exceptions import DocumentError
from apps.documents.retrieval_adapter import retrieve_authorized
from apps.documents.retrieval_scope import resolve_scope
from common.testing import authenticate_client
from tests.documents.test_retrieval_scope import ScopeFixture


class SessionAccessTests(ScopeFixture):
    def setUp(self):
        super().setUp()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        storage = override_settings(DOCUMENTS_STORAGE_ROOT=Path(folder.name))
        storage.enable()
        self.addCleanup(storage.disable)
        self.content = b'%PDF-1.4\naccess-test\n%%EOF\n'
        original = Path(folder.name) / 'access.pdf'
        original.write_bytes(self.content)
        self.version.original_storage_key = 'access.pdf'
        self.version.checksum_sha256 = hashlib.sha256(self.content).hexdigest()
        self.version.save()
        self.doc.material_policy = 'PUBLIC_DOWNLOAD'
        self.doc.save()
        self.client = authenticate_client(APIClient(), self.student)
        self.owner_client = authenticate_client(APIClient(), self.owner)
        self.sessions_url = f'/api/courses/{self.course.pk}/classrooms/{self.classroom.pk}/sessions/'
        self.documents_url = f'/api/courses/{self.course.pk}/documents/'
        self.base = f'/api/documents/{self.doc.pk}/'

    def urls(self):
        return [self.base + suffix for suffix in ('status/', 'view/', 'download/')] + [
            self.base + f'study-notes/?version_id={self.version.pk}']

    def assert_document_hidden(self):
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_student_does_not_list_draft_sessions_or_their_materials(self):
        self.session.is_draft = True
        self.session.save()
        self.assertEqual(self.client.get(self.sessions_url).json()['results'], [])
        self.assertEqual(self.client.get(self.documents_url).json()['results'], [])
        self.assertEqual(self.client.get(self.documents_url + f'?session_id={self.session.pk}').status_code, 404)

    def test_draft_document_direct_urls_and_notes_write_are_denied(self):
        self.session.is_draft = True
        self.session.save()
        self.assert_document_hidden()
        self.assertEqual(self.client.put(self.base + f'study-notes/?version_id={self.version.pk}', {}, format='json').status_code, 404)

    def test_owner_retains_draft_preview_and_management(self):
        self.session.is_draft = True
        self.session.save()
        self.assertEqual(self.owner_client.get(self.sessions_url).json()['results'][0]['id'], str(self.session.pk))
        self.assertEqual(self.owner_client.get(self.documents_url).json()['results'][0]['document_id'], str(self.doc.pk))
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.owner_client.get(url).status_code, 200)
        scope = resolve_scope(self.owner, self.course.pk, session_id=self.session.pk, preview=True)
        self.assertEqual(scope.allowed_version_ids, (str(self.version.pk),))
        with self.assertRaises(DocumentError):
            resolve_scope(self.student, self.course.pk, session_id=self.session.pk, preview=True)
        self.assertEqual(self.owner_client.patch(self.base, {'title': 'Draft title'}, format='json').status_code, 200)

    def test_finalizing_session_makes_published_material_visible(self):
        self.session.is_draft = True
        self.session.save()
        self.assert_document_hidden()
        response = self.owner_client.patch(self.sessions_url + str(self.session.pk) + '/', {'is_draft': False}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.client.get(self.sessions_url).json()['results']), 1)
        self.assertEqual(self.client.get(self.documents_url).json()['results'][0]['document_id'], str(self.doc.pk))
        response = self.client.get(self.base + 'view/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.content)
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_draft_sources_are_excluded_from_every_student_retrieval_scope(self):
        self.session.is_draft = True
        self.session.save()
        for kwargs in ({}, {'classroom_id': self.classroom.pk}, {'document_ids': [str(self.doc.pk)]}):
            with self.subTest(scope=kwargs):
                self.assertEqual(resolve_scope(self.student, self.course.pk, **kwargs).allowed_version_ids, ())
        with self.assertRaises(DocumentError):
            resolve_scope(self.student, self.course.pk, session_id=self.session.pk)

    def test_draft_chat_and_conversation_do_not_call_model(self):
        self.session.is_draft = True
        self.session.save()
        selector = dict(course_id=str(self.course.pk), session_id=str(self.session.pk), document_id=str(self.doc.pk))
        with patch('apps.ai.services.get_runtime') as runtime:
            response = self.client.post('/api/ai/chat/', dict(course_id=str(self.course.pk), session_id=str(self.session.pk),
                document_ids=[str(self.doc.pk)], question='Question', mode='qa'), format='json')
            self.assertEqual(response.status_code, 404)
            self.assertEqual(self.client.post('/api/ai/conversations/', selector, format='json').status_code, 404)
            runtime.assert_not_called()

    def test_withdrawn_student_cannot_use_old_urls_even_when_enrolled_elsewhere(self):
        other = Classroom.objects.create(course=self.course, name='Other classroom')
        Enrollment.objects.create(classroom=other, student=self.student.student_profile)
        self.enrollment.status = 'WITHDRAWN'
        self.enrollment.save()
        self.assertEqual(self.client.get(self.sessions_url).status_code, 404)
        self.assert_document_hidden()
        self.assertEqual(self.client.get(self.documents_url).json()['results'], [])
        self.assertEqual(resolve_scope(self.student, self.course.pk).allowed_version_ids, ())

    def test_removed_membership_blocks_api_and_scope(self):
        self.member.status = 'REMOVED'
        self.member.save()
        self.assert_document_hidden()
        self.assertEqual(self.client.get(self.documents_url).status_code, 404)
        with self.assertRaises(DocumentError):
            resolve_scope(self.student, self.course.pk)

    def test_other_teacher_and_unrelated_student_cannot_access(self):
        from apps.users.models import User
        for role in ('TEACHER', 'STUDENT'):
            user = approved_teacher(User.objects.create_user('foreign-' + role.lower(), role=role))
            self.client = authenticate_client(APIClient(), user)
            self.assertEqual(self.client.get(self.sessions_url).status_code, 404)
            self.assert_document_hidden()

    def test_removed_session_hides_course_listing_and_old_media(self):
        self.session.removed_at = timezone.now()
        self.session.save()
        self.assert_document_hidden()
        self.assertEqual(self.client.get(self.sessions_url).json()['results'], [])
        self.assertEqual(self.client.get(self.documents_url).json()['results'], [])
        self.assertEqual(self.owner_client.get(self.documents_url).json()['results'], [])

    def test_removed_classroom_hides_documents_and_sources(self):
        self.classroom.removed_at = timezone.now()
        self.classroom.save()
        self.assert_document_hidden()
        self.assertEqual(self.client.get(self.sessions_url).status_code, 404)
        self.assertEqual(self.client.get(self.documents_url).json()['results'], [])
        self.assertEqual(resolve_scope(self.student, self.course.pk).allowed_version_ids, ())

    def test_unpublished_or_removed_document_cannot_reuse_old_urls(self):
        self.doc.is_published = False
        self.doc.save()
        self.assert_document_hidden()
        self.assertEqual(self.client.get(self.documents_url).json()['results'], [])
        self.doc.removed_at = timezone.now()
        self.doc.save()
        self.assert_document_hidden()

    def test_unpublished_replacement_does_not_expose_new_version(self):
        from apps.documents.models import DocumentVersion
        newer = DocumentVersion.objects.create(document=self.doc, version_number=2, file_name='new.pdf',
            original_storage_key='new.pdf', file_size_bytes=1, checksum_sha256='b'*64, page_count=1, status='EXTRACTED')
        self.doc.active_version = newer
        self.doc.save()
        self.assertEqual(self.client.get(self.base + f'status/?version_id={newer.pk}').status_code, 404)
        response = self.client.get(self.base + f'view/?expected_version_id={newer.pk}')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get(self.base + f'view/?expected_version_id={self.version.pk}').status_code, 200)

    def test_removed_published_version_is_not_listed_or_counted(self):
        self.version.removed_at = timezone.now()
        self.version.save()
        self.assertEqual(self.client.get(self.documents_url).json()['results'], [])
        self.assertEqual(self.client.get(self.sessions_url).json()['results'][0]['material_count'], 0)
        self.assertEqual(self.client.get(self.base + 'status/').status_code, 404)
        self.assertIn(self.client.get(self.base + 'view/').status_code, (404, 409))
        self.assertEqual(resolve_scope(self.student, self.course.pk).allowed_version_ids, ())

    def test_course_level_document_remains_accessible_to_active_course_member(self):
        self.doc.session = None
        self.doc.save()
        self.session.is_draft = True
        self.session.save()
        self.assertEqual(self.client.get(self.documents_url + '?scope=course').json()['results'][0]['document_id'], str(self.doc.pk))
        self.assertEqual(self.client.get(self.base + 'status/').status_code, 200)
        self.assertEqual(self.client.get(self.base + 'view/').status_code, 200)
        self.assertEqual(resolve_scope(self.student, self.course.pk).allowed_version_ids, (str(self.version.pk),))

    def test_existing_conversation_is_denied_after_withdrawal(self):
        selector = dict(course_id=str(self.course.pk), session_id=str(self.session.pk), document_id=str(self.doc.pk))
        response = self.client.post('/api/ai/conversations/', selector, format='json')
        self.assertEqual(response.status_code, 201)
        conversation_id = response.json()['id']
        self.enrollment.status = 'WITHDRAWN'
        self.enrollment.save()
        self.assertEqual(self.client.get(f'/api/ai/conversations/{conversation_id}/').status_code, 404)

    def test_revocation_during_retrieval_prevents_context_release(self):
        scope = resolve_scope(self.student, self.course.pk, session_id=self.session.pk)
        retriever = Mock()
        def withdraw(**kwargs):
            Enrollment.objects.filter(pk=self.enrollment.pk).update(status='WITHDRAWN')
            return []
        retriever.search.side_effect = withdraw
        with self.assertRaises(DocumentError):
            retrieve_authorized(self.student, 'Question', scope, retriever, catalog={})
        retriever.search.assert_called_once()

    def test_session_or_classroom_change_during_pdf_read_is_rechecked(self):
        from apps.courses.models import ClassroomSession, Course
        changes = [
            (ClassroomSession.objects.filter(pk=self.session.pk), {'is_draft': True}),
            (ClassroomSession.objects.filter(pk=self.session.pk), {'removed_at': timezone.now()}),
            (Classroom.objects.filter(pk=self.classroom.pk), {'removed_at': timezone.now()}),
            (Course.objects.filter(pk=self.course.pk), {'status': 'ARCHIVED'}),
        ]
        for queryset, update in changes:
            with self.subTest(change=update):
                ClassroomSession.objects.filter(pk=self.session.pk).update(is_draft=False, removed_at=None)
                Classroom.objects.filter(pk=self.classroom.pk).update(removed_at=None)
                Course.objects.filter(pk=self.course.pk).update(status='PUBLISHED')
                path = Mock()
                def changed_content():
                    queryset.update(**update)
                    return self.content
                path.read_bytes.side_effect = changed_content
                with patch('apps.documents.api.views.private_path', return_value=path):
                    self.assertEqual(self.client.get(self.base + 'view/').status_code, 404)
