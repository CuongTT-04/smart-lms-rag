"""W9-GR-01 access-control matrix, stale URL, policy, version and mid-turn revocation tests."""
import hashlib
import io
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch
import uuid

from django.test import TestCase, override_settings
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from apps.ai.conversations import send_conversation
from apps.ai.models import ChatConversation, ChatTurn, SummaryTask
from apps.ai.services import answer_chat
from apps.courses.models import Enrollment
from apps.documents.exceptions import DocumentError
from apps.documents.models import KnowledgeDocument
from apps.documents.retrieval_adapter import assert_scope_and_citations_live, live_scope
from apps.documents.retrieval_scope import resolve_scope, verify_citation_access
from apps.documents.services import remove_document, set_material_policy, set_publication
from apps.documents.storage import private_path
from apps.users.models import User
from common.testing import authenticate_client
from tests.documents.w9_guardrails_fixture import SENTINELS, build_w9_guardrails_fixture


class _FakeRuntime:
    def __init__(self, fixture, *, generate_fn=None):
        self.catalog = fixture.catalog
        self.index = Mock()
        self.embedding = Mock()
        self.config = {'model': 'w9-mock', 'max_input_tokens': 4096}
        self.generate = Mock(side_effect=generate_fn or self._default_generate)

    @staticmethod
    def _default_generate(**kwargs):
        first = kwargs['contexts'][0]
        output = {
            'status': 'ANSWERED',
            'answer': 'Chu ky lenh CPU gom nap, giai ma va thuc thi [1].',
            'references': [{'label': 1, 'source_id': first['source_id']}],
            'usage': {'input_tokens': 42, 'output_tokens': 16},
        }
        if kwargs.get('history') is not None:
            output['_memory'] = {
                'protocol': 'chat_history_v1',
                'turns_used': len(kwargs['history']),
                'turns_dropped': 0,
                'history_tokens': 0,
            }
        return output


class W9GuardrailsAccessTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        storage = override_settings(DOCUMENTS_STORAGE_ROOT=Path(folder.name))
        storage.enable()
        self.addCleanup(storage.disable)
        self.fx = build_w9_guardrails_fixture()
        self.clients = {
            'teacher_main': authenticate_client(APIClient(), self.fx.teacher_main),
            'teacher_other': authenticate_client(APIClient(), self.fx.teacher_other),
            'student_a': authenticate_client(APIClient(), self.fx.student_a),
            'student_b': authenticate_client(APIClient(), self.fx.student_b),
            'admin_summary': authenticate_client(APIClient(), self.fx.admin_summary),
        }

    def _hit_for(self, version):
        chunk_id = f'w9gr:{version.pk}:p1:c1'
        chunk = self.fx.catalog[chunk_id]
        return {
            'chunk_id': chunk_id,
            'score': 0.98,
            'text': chunk.text,
            'source': {
                'course_id': chunk.course_id,
                'document_id': chunk.document_id,
                'version_id': chunk.version_id,
                'document_title': chunk.document_title,
                'page_number': chunk.page_number,
                'section_title': chunk.section_title,
            },
        }

    def test_permission_matrix_across_roles_and_no_store_headers(self):
        doc = self.fx.doc_allowed
        ver = self.fx.doc_allowed_v1
        base = f'/api/documents/{doc.pk}/'
        course_docs_url = f'/api/courses/{self.fx.course_main.pk}/documents/'

        # Allowed student_a: sees only Classroom A published docs, never Classroom B / removed / draft / other course.
        listing = self.clients['student_a'].get(course_docs_url)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing['Cache-Control'], 'private, no-store')
        returned_ids = {row['document_id'] for row in listing.json()['results']}
        self.assertEqual(returned_ids, {str(self.fx.doc_allowed.pk), str(self.fx.doc_versioned.pk)})
        self.assertNotIn(str(self.fx.doc_classroom_b.pk), returned_ids)
        self.assertNotIn(str(self.fx.doc_removed.pk), returned_ids)
        self.assertNotIn(str(self.fx.doc_draft_session.pk), returned_ids)

        status_resp = self.clients['student_a'].get(base + 'status/')
        self.assertEqual(status_resp.status_code, 200)
        self.assertEqual(status_resp['Cache-Control'], 'private, no-store')

        view_resp = self.clients['student_a'].get(base + f'view/?expected_version_id={ver.pk}')
        self.assertEqual(view_resp.status_code, 200)
        self.assertEqual(view_resp['Cache-Control'], 'private, no-store')
        self.assertEqual(view_resp['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(view_resp['X-Document-Version'], str(ver.pk))
        pdf_text = PdfReader(io.BytesIO(view_resp.content)).pages[0].extract_text()
        self.assertIn(self.fx.student_a.email, pdf_text)
        self.assertIn(SENTINELS['allowed_p1'], pdf_text)

        self.assertEqual(self.clients['student_a'].get(base + 'download/').status_code, 403)
        self.assertEqual(self.clients['student_a'].get(base + 'extraction/').status_code, 404)
        notes_resp = self.clients['student_a'].get(base + f'study-notes/?version_id={ver.pk}')
        self.assertEqual(notes_resp.status_code, 200)
        self.assertEqual(notes_resp['Cache-Control'], 'private, no-store')

        # Course owner teacher_main: allowed everywhere including clean download & extraction.
        ext_resp = self.clients['teacher_main'].get(base + 'extraction/')
        self.assertEqual(ext_resp.status_code, 200)
        self.assertEqual(ext_resp['Cache-Control'], 'private, no-store')
        dl_resp = self.clients['teacher_main'].get(base + 'download/')
        self.assertEqual(dl_resp.status_code, 200)
        self.assertEqual(hashlib.sha256(dl_resp.content).hexdigest(), ver.checksum_sha256)

        # Forbidden roles on Classroom A's document: student_b, teacher_other, admin_summary.
        for actor_name in ('student_b', 'teacher_other', 'admin_summary'):
            client = self.clients[actor_name]
            for path in (
                base + 'status/',
                base + 'view/',
                base + f'view/?expected_version_id={ver.pk}',
                base + 'download/',
                base + 'extraction/',
                base + f'study-notes/?version_id={ver.pk}',
            ):
                with self.subTest(actor=actor_name, path=path):
                    resp = client.get(path)
                    self.assertEqual(resp.status_code, 404)
                    body = resp.content.decode('utf-8', errors='ignore')
                    self.assertNotIn(doc.title, body)
                    self.assertNotIn(SENTINELS['allowed_p1'], body)

        # Admin summary & other teacher cannot list course_main documents or resolve scope.
        for actor_name, user in (('teacher_other', self.fx.teacher_other), ('admin_summary', self.fx.admin_summary)):
            self.assertEqual(self.clients[actor_name].get(course_docs_url).status_code, 404)
            with self.assertRaises(DocumentError) as caught:
                resolve_scope(user, self.fx.course_main.pk)
            self.assertEqual(caught.exception.status, 404)

        # Cross-classroom scope isolation inside the same course.
        scope_a = resolve_scope(self.fx.student_a, self.fx.course_main.pk)
        scope_b = resolve_scope(self.fx.student_b, self.fx.course_main.pk)
        self.assertEqual(set(scope_a.allowed_version_ids), {str(self.fx.doc_allowed_v1.pk), str(self.fx.doc_versioned_v1.pk)})
        self.assertEqual(scope_b.allowed_version_ids, (str(self.fx.doc_classroom_b_v1.pk),))

    def test_policy_switch_and_toctou_during_file_io_block_clean_download(self):
        doc = self.fx.doc_allowed
        ver = self.fx.doc_allowed_v1
        base = f'/api/documents/{doc.pk}/'

        # Enable public download -> student can download clean file.
        set_material_policy(self.fx.teacher_main, doc, 'PUBLIC_DOWNLOAD', doc.policy_revision)
        doc.refresh_from_db()
        clean = self.clients['student_a'].get(base + 'download/')
        self.assertEqual(clean.status_code, 200)
        self.assertEqual(hashlib.sha256(clean.content).hexdigest(), ver.checksum_sha256)

        # Switch back to PROTECTED mid-read during file I/O -> clean download must be rejected (403).
        original_bytes = private_path(ver.original_storage_key).read_bytes()
        path_mock = Mock()
        def flip_to_protected():
            KnowledgeDocument.objects.filter(pk=doc.pk).update(material_policy='PROTECTED', policy_revision=doc.policy_revision + 1)
            return original_bytes
        path_mock.read_bytes.side_effect = flip_to_protected
        with patch('apps.documents.api.views.private_path', return_value=path_mock):
            resp = self.clients['student_a'].get(base + 'download/')
        self.assertEqual(resp.status_code, 403)

        # Also if flipped during unwatermarked view -> rejected with 409 SCOPE_CHANGED.
        KnowledgeDocument.objects.filter(pk=doc.pk).update(material_policy='PUBLIC_DOWNLOAD', policy_revision=10)
        path_mock2 = Mock()
        def flip_during_view():
            KnowledgeDocument.objects.filter(pk=doc.pk).update(material_policy='PROTECTED', policy_revision=11)
            return original_bytes
        path_mock2.read_bytes.side_effect = flip_during_view
        with patch('apps.documents.api.views.private_path', return_value=path_mock2):
            resp = self.clients['student_a'].get(base + 'view/')
        self.assertEqual(resp.status_code, 409)

    def test_version_replacement_invalidates_old_citation_urls_notes_and_history(self):
        doc = self.fx.doc_versioned
        v1 = self.fx.doc_versioned_v1
        v2 = self.fx.doc_versioned_v2
        base = f'/api/documents/{doc.pk}/'

        # Before publishing v2: student_a sees v1, cannot open v2 via expected_version_id or citation check.
        self.assertEqual(self.clients['student_a'].get(base + f'view/?expected_version_id={v1.pk}').status_code, 200)
        self.assertEqual(self.clients['student_a'].get(base + f'view/?expected_version_id={v2.pk}').status_code, 409)
        with self.assertRaises(DocumentError) as caught:
            verify_citation_access(self.fx.student_a, document_id=doc.pk, version_id=v2.pk, page_number=1)
        self.assertEqual(caught.exception.status, 409)

        # Create a v1 conversation while v1 is published.
        convo_resp = self.clients['student_a'].post('/api/ai/conversations/', {
            'course_id': str(self.fx.course_main.pk),
            'classroom_id': str(self.fx.classroom_a.pk),
            'session_id': str(self.fx.session_a.pk),
            'document_id': str(doc.pk),
        }, format='json')
        self.assertEqual(convo_resp.status_code, 201)
        convo_id = convo_resp.json()['id']

        # Publish v2 (3 pages) -> old v1 citation URL, v1 citation check, v1 notes, and v1 conversation all stop serving v1.
        set_publication(self.fx.teacher_main, doc, True, str(v2.pk))
        self.assertEqual(self.clients['student_a'].get(base + f'view/?expected_version_id={v1.pk}').status_code, 409)
        self.assertEqual(self.clients['student_a'].get(base + f'study-notes/?version_id={v1.pk}').status_code, 404)
        self.assertEqual(self.clients['student_a'].get(f'/api/ai/conversations/{convo_id}/').status_code, 404)

        with self.assertRaises(DocumentError) as old_cite:
            verify_citation_access(self.fx.student_a, document_id=doc.pk, version_id=v1.pk, page_number=1)
        self.assertEqual(old_cite.exception.status, 409)

        # v2 page 3 is now valid; out-of-range page 4 fails closed.
        resolved_doc, resolved_ver = verify_citation_access(
            self.fx.student_a, document_id=doc.pk, version_id=v2.pk, page_number=3,
        )
        self.assertEqual((resolved_doc.pk, resolved_ver.pk), (doc.pk, v2.pk))
        with self.assertRaises(DocumentError) as bad_page:
            verify_citation_access(self.fx.student_a, document_id=doc.pk, version_id=v2.pk, page_number=4)
        self.assertEqual(bad_page.exception.status, 409)

    def test_removal_and_enrollment_revocation_block_old_urls_history_and_summary(self):
        doc = self.fx.doc_allowed
        ver = self.fx.doc_allowed_v1
        base = f'/api/documents/{doc.pk}/'

        # Open a valid conversation and create a completed summary task while student_a has access.
        convo = ChatConversation.objects.create(
            user=self.fx.student_a,
            course=self.fx.course_main,
            classroom=self.fx.classroom_a,
            classroom_session=self.fx.session_a,
            document=doc,
            version=ver,
            title='Cau hoi CPU cu',
        )
        ChatTurn.objects.create(
            conversation=convo,
            client_message_id=uuid.uuid4(),
            position=1,
            question='Chu ky lenh?',
            status='COMPLETED',
            result={'status': 'ANSWERED', 'answer': 'Nap lenh [1].', 'citations': []},
        )
        summary = SummaryTask.objects.create(
            user=self.fx.student_a,
            client_request_id=str(uuid.uuid4()),
            document=doc,
            version=ver,
            selector={
                'course_id': str(self.fx.course_main.pk),
                'classroom_id': str(self.fx.classroom_a.pk),
                'session_id': str(self.fx.session_a.pk),
                'document_ids': [str(doc.pk)],
            },
            status='COMPLETED',
            state={'checksum': ver.checksum_sha256, 'start': 1, 'end': 1, 'pages': ver.page_count, 'blocks': [], 'cursor': 0, 'steps': 1},
            result={'status': 'ANSWERED', 'answer': 'Tom tat cu', 'citations': [], 'timing': {'total_ms': 10}, 'coverage': {'citation_scope': 'input_range'}},
        )

        # Baseline: student_a can open URL, conversation history and summary.
        self.assertEqual(self.clients['student_a'].get(base + f'view/?expected_version_id={ver.pk}').status_code, 200)
        self.assertEqual(self.clients['student_a'].get(f'/api/ai/conversations/{convo.pk}/').status_code, 200)
        self.assertEqual(self.clients['student_a'].get(f'/api/ai/summaries/{summary.pk}/').status_code, 200)

        # Revoke classroom enrollment -> every channel immediately fails closed.
        Enrollment.objects.filter(pk=self.fx.enrollment_a.pk).update(status='WITHDRAWN')
        for url in (
            base + 'status/',
            base + 'view/',
            base + f'view/?expected_version_id={ver.pk}',
            base + 'download/',
            base + f'study-notes/?version_id={ver.pk}',
            f'/api/ai/conversations/{convo.pk}/',
            f'/api/ai/summaries/{summary.pk}/',
        ):
            with self.subTest(revoked_url=url):
                self.assertEqual(self.clients['student_a'].get(url).status_code, 404)

        # Restore enrollment, then remove document -> old URLs, citations, history & summary stay blocked.
        Enrollment.objects.filter(pk=self.fx.enrollment_a.pk).update(status='ACTIVE')
        remove_document(self.fx.teacher_main, doc)
        for url in (
            base + 'status/',
            base + f'view/?expected_version_id={ver.pk}',
            f'/api/ai/conversations/{convo.pk}/',
            f'/api/ai/summaries/{summary.pk}/',
        ):
            with self.subTest(removed_url=url):
                self.assertEqual(self.clients['student_a'].get(url).status_code, 404)

    def test_mid_turn_revocation_after_retrieval_prevents_model_call(self):
        doc = self.fx.doc_allowed
        ver = self.fx.doc_allowed_v1
        mutations = (
            ('withdraw_enrollment', lambda: Enrollment.objects.filter(pk=self.fx.enrollment_a.pk).update(status='WITHDRAWN'), 404),
            ('remove_document', lambda: KnowledgeDocument.objects.filter(pk=doc.pk).update(removed_at=timezone.now(), is_published=False, published_version=None), 404),
            ('block_user_raw_update', lambda: User.objects.filter(pk=self.fx.student_a.pk).update(status='BLOCKED', is_active=False), 401),
        )
        for name, mutate, expected_status in mutations:
            with self.subTest(mutation=name):
                # Reset clean baseline before each subTest.
                Enrollment.objects.filter(pk=self.fx.enrollment_a.pk).update(status='ACTIVE')
                KnowledgeDocument.objects.filter(pk=doc.pk).update(removed_at=None, is_published=True, published_version=ver)
                User.objects.filter(pk=self.fx.student_a.pk).update(status='ACTIVE', is_active=True)
                self.fx.student_a.refresh_from_db()

                runtime = _FakeRuntime(self.fx)
                def retrieve_then_revoke(user, query, scope, *args, **kwargs):
                    # Simulate mutation happening right after retrieval and before prompt leaves backend.
                    mutate()
                    live_scope(user, scope)
                    return [self._hit_for(ver)]

                with patch('apps.ai.services.retrieve_dense_authorized', side_effect=retrieve_then_revoke):
                    with self.assertRaises(DocumentError) as caught:
                        answer_chat(
                            user=self.fx.student_a,
                            data={
                                'course_id': str(self.fx.course_main.pk),
                                'classroom_id': str(self.fx.classroom_a.pk),
                                'session_id': str(self.fx.session_a.pk),
                                'document_ids': [str(doc.pk)],
                                'question': 'Chu ky lenh CPU gom nhung buoc nao?',
                                'mode': 'qa',
                            },
                            request_id=str(uuid.uuid4()),
                            runtime=runtime,
                        )
                self.assertEqual(caught.exception.status, expected_status)
                runtime.generate.assert_not_called()

    def test_mid_turn_revocation_after_model_blocks_response_and_prevents_history_persistence(self):
        doc = self.fx.doc_allowed
        ver = self.fx.doc_allowed_v1
        mutations = (
            ('withdraw_enrollment', lambda: Enrollment.objects.filter(pk=self.fx.enrollment_a.pk).update(status='WITHDRAWN'), 404),
            ('unpublish_document', lambda: KnowledgeDocument.objects.filter(pk=doc.pk).update(is_published=False, published_version=None), 409),
            ('block_user', lambda: User.objects.filter(pk=self.fx.student_a.pk).update(status='BLOCKED', is_active=False), 401),
        )
        for name, mutate, expected_status in mutations:
            with self.subTest(mutation=name):
                Enrollment.objects.filter(pk=self.fx.enrollment_a.pk).update(status='ACTIVE')
                KnowledgeDocument.objects.filter(pk=doc.pk).update(removed_at=None, is_published=True, published_version=ver)
                User.objects.filter(pk=self.fx.student_a.pk).update(status='ACTIVE', is_active=True)
                self.fx.student_a.refresh_from_db()

                convo = ChatConversation.objects.create(
                    user=self.fx.student_a,
                    course=self.fx.course_main,
                    classroom=self.fx.classroom_a,
                    classroom_session=self.fx.session_a,
                    document=doc,
                    version=ver,
                )

                def generate_then_revoke(**kwargs):
                    result = _FakeRuntime._default_generate(**kwargs)
                    mutate()
                    return result

                runtime = _FakeRuntime(self.fx, generate_fn=generate_then_revoke)
                with patch('apps.ai.services.get_runtime', return_value=runtime), \
                     patch('apps.ai.services.retrieve_dense_authorized', return_value=[self._hit_for(ver)]):
                    with self.assertRaises(DocumentError) as caught:
                        send_conversation(
                            user=self.fx.student_a,
                            data={
                                'conversation_id': str(convo.pk),
                                'client_message_id': str(uuid.uuid4()),
                                'question': 'Chu ky lenh CPU gom nhung buoc nao?',
                            },
                        )
                self.assertEqual(caught.exception.status, expected_status)
                runtime.generate.assert_called_once()
                turn = convo.turns.get()
                self.assertEqual(turn.status, 'FAILED')
                self.assertIsNone(turn.result)
                # Also verify conversation cannot be read back after revocation.
                self.assertIn(self.clients['student_a'].get(f'/api/ai/conversations/{convo.pk}/').status_code, (401, 404))

    def test_citation_contract_and_active_test_blocking(self):
        scope_a = resolve_scope(
            self.fx.student_a,
            self.fx.course_main.pk,
            classroom_id=self.fx.classroom_a.pk,
            session_id=self.fx.session_a.pk,
        )
        # Valid citation passes live gate.
        assert_scope_and_citations_live(
            self.fx.student_a,
            scope_a,
            citations=[{
                'document_id': str(self.fx.doc_allowed.pk),
                'version_id': str(self.fx.doc_allowed_v1.pk),
                'page_number': 1,
            }],
        )
        # Cross-classroom citation fails with 404.
        with self.assertRaises(DocumentError) as cross:
            assert_scope_and_citations_live(
                self.fx.student_a,
                scope_a,
                citations=[{
                    'document_id': str(self.fx.doc_classroom_b.pk),
                    'version_id': str(self.fx.doc_classroom_b_v1.pk),
                    'page_number': 1,
                }],
            )
        self.assertEqual(cross.exception.status, 404)

        # Active TEST attempt blocks AI before retrieval/model while preserving document access rules.
        self.fx.start_active_test_attempt(self.fx.student_a)
        with patch('apps.ai.services.get_runtime') as runtime:
            resp = self.clients['student_a'].post('/api/ai/chat/', {
                'course_id': str(self.fx.course_main.pk),
                'classroom_id': str(self.fx.classroom_a.pk),
                'session_id': str(self.fx.session_a.pk),
                'document_ids': [str(self.fx.doc_allowed.pk)],
                'question': 'Goi y bai kiem tra?',
                'mode': 'qa',
            }, format='json')
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.json()['code'], 'AI_NOT_ALLOWED')
            runtime.assert_not_called()
