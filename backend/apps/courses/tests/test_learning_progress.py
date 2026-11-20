from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import uuid
from unittest.mock import patch

from django.core.management import call_command
from django.db import connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.courses.assessment_models import Assessment, AssessmentAttempt
from apps.courses.enrollment_services import join_by_code, withdraw_classroom_enrollment
from apps.courses.models import Classroom, ClassroomSession, Enrollment
from apps.courses.progress_models import DocumentCompletion
from apps.courses.progress_services import (
    classroom_progress,
    mark_document_complete,
    refresh_classroom_progress,
)
from apps.courses.services import create_course, update_course
from apps.courses.video_models import SessionVideo, VideoProgress
from apps.documents.models import DocumentVersion, KnowledgeDocument
from apps.users.models import User


def _setup_classroom_fixture():
    teacher = User.objects.create_user(f't-{uuid.uuid4().hex[:8]}', role='TEACHER')
    student_a = User.objects.create_user(f'sa-{uuid.uuid4().hex[:8]}', role='STUDENT')
    student_b = User.objects.create_user(f'sb-{uuid.uuid4().hex[:8]}', role='STUDENT')
    course = create_course(actor=teacher, title='Kiến trúc máy tính')
    update_course(actor=teacher, course=course, changes={'status': 'PUBLISHED'})
    room = Classroom.objects.create(course=course, name='Lớp W9')
    _, enrollment_a, _ = join_by_code(actor=student_a, class_code=room.class_code)
    _, enrollment_b, _ = join_by_code(actor=student_b, class_code=room.class_code)
    session = ClassroomSession.objects.create(classroom=room, title='Buổi 1', is_draft=False)
    return teacher, student_a, student_b, course, room, enrollment_a, enrollment_b, session


def _create_published_pdf(teacher, course, session, title='Tài liệu PDF'):
    doc = KnowledgeDocument.objects.create(
        course=course,
        session=session,
        uploaded_by=teacher,
        title=title,
        is_published=True,
    )
    ver = DocumentVersion.objects.create(
        document=doc,
        version_number=1,
        file_name='doc.pdf',
        file_size_bytes=100,
        checksum_sha256='0' * 64,
        page_count=5,
        original_storage_key='originals/doc.pdf',
        status='EXTRACTED',
    )
    doc.active_version = ver
    doc.published_version = ver
    doc.save(update_fields=['active_version', 'published_version'])
    return doc, ver


def _create_published_video(session, title='Video bài giảng'):
    return SessionVideo.objects.create(
        session=session,
        title=title,
        file='videos/sample.mp4',
        content_type='video/mp4',
        duration=120.0,
        is_published=True,
    )


def _create_published_assessment(session, kind='QUIZ', mode='PRACTICE', title='Bài tập'):
    return Assessment.objects.create(
        session=session,
        title=title,
        kind=kind,
        mode=mode,
        questions=[{'id': 'q1', 'prompt': '1+1?', 'choices': [{'id': 'a', 'text': '2'}], 'correct_ids': ['a']}]
        if kind == 'QUIZ'
        else [],
        due_at=timezone.now() + timedelta(days=3),
        is_published=True,
    )


class LearningProgressServiceTests(TestCase):
    def test_document_publication_and_removal_sync_saved_enrollment(self):
        from apps.documents.services import remove_document, set_publication

        def mutate(operation, *args):
            with patch('apps.courses.progress_services.refresh_classroom_progress', wraps=refresh_classroom_progress) as refresh:
                with self.captureOnCommitCallbacks(execute=True):
                    operation(*args)
                    refresh.assert_not_called()
                refresh.assert_called_once_with(classroom_id=room.pk)

        teacher, student, _, course, room, enrollment, _, session = _setup_classroom_fixture()
        document, version = _create_published_pdf(teacher, course, session)
        version.watermark_status = 'READY'
        version.watermarked_view_key = 'views/one.pdf'
        version.save()
        mark_document_complete(actor=student, classroom_id=room.pk, version_id=version.pk)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.COMPLETED)

        mutate(set_publication, teacher, document, False)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertEqual(enrollment.progress_percent, 0)
        self.assertIsNone(enrollment.completed_at)

        next_version = DocumentVersion.objects.create(
            document=document, version_number=2, file_name='new.pdf', file_size_bytes=100,
            checksum_sha256='1' * 64, page_count=1, original_storage_key='originals/new.pdf',
            status='EXTRACTED', watermark_status='READY', watermarked_view_key='views/two.pdf',
        )
        with patch('apps.documents.services.private_path') as storage:
            storage.return_value.is_file.return_value = True
            mutate(set_publication, teacher, document, True, version.pk)
            enrollment.refresh_from_db()
            self.assertEqual(enrollment.status, Enrollment.Status.COMPLETED)
            mutate(set_publication, teacher, document, True, next_version.pk)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertIsNone(enrollment.completed_at)
        mark_document_complete(actor=student, classroom_id=room.pk, version_id=next_version.pk)
        mutate(remove_document, teacher, document)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertEqual(enrollment.progress_percent, 0)
        self.assertIsNone(enrollment.completed_at)

    def test_empty_classroom_progress_and_draft_exclusion(self):
        teacher, student_a, _, course, room, enrollment_a, _, session = _setup_classroom_fixture()
        draft_session = ClassroomSession.objects.create(classroom=room, title='Nháp', is_draft=True)
        _create_published_pdf(teacher, course, draft_session, 'PDF trong buổi nháp')
        KnowledgeDocument.objects.create(
            course=course, session=session, uploaded_by=teacher, title='PDF nháp', is_published=False
        )
        SessionVideo.objects.create(
            session=session, title='Video nháp', file='v.mp4', content_type='video/mp4', duration=10, is_published=False
        )
        Assessment.objects.create(
            session=session, title='Quiz nháp', kind='QUIZ', mode='PRACTICE',
            due_at=timezone.now() + timedelta(days=1), is_published=False,
        )

        progress = classroom_progress(actor=student_a, classroom_id=room.pk)
        self.assertEqual(progress['total_activities'], 0)
        self.assertEqual(progress['completed_activities'], 0)
        self.assertEqual(progress['percent'], 0.0)
        self.assertFalse(progress['has_activities'])
        self.assertIsNone(progress['completed_at'])
        enrollment_a.refresh_from_db()
        self.assertEqual(enrollment_a.status, Enrollment.Status.ACTIVE)

    def test_four_activity_lifecycle_version_change_and_removal(self):
        teacher, student_a, student_b, course, room, enrollment_a, enrollment_b, session = _setup_classroom_fixture()
        doc, v1 = _create_published_pdf(teacher, course, session)
        video = _create_published_video(session)
        quiz = _create_published_assessment(session, kind='QUIZ', title='Quiz 1')
        essay = _create_published_assessment(session, kind='TEXT', title='Tự luận 1')

        # Draft essay does not count; submitted quiz with score 0 counts.
        AssessmentAttempt.objects.create(
            assessment=essay, student=student_a, request_id=uuid.uuid4(), number=1,
            status='DRAFT', expires_at=timezone.now() + timedelta(days=1),
        )
        AssessmentAttempt.objects.create(
            assessment=quiz, student=student_a, request_id=uuid.uuid4(), number=1,
            status='SUBMITTED', submitted_at=timezone.now(), score=0,
            expires_at=timezone.now() + timedelta(days=1),
        )
        progress = mark_document_complete(actor=student_a, classroom_id=room.pk, version_id=v1.pk)
        self.assertEqual(progress['total_activities'], 4)
        self.assertEqual(progress['completed_activities'], 2)
        self.assertEqual(progress['percent'], 50.0)
        self.assertTrue(progress['has_activities'])
        self.assertIsNone(progress['completed_at'])

        # Duplicate PDF completion does not inflate count.
        repeat = mark_document_complete(actor=student_a, classroom_id=room.pk, version_id=v1.pk)
        self.assertEqual(repeat['completed_activities'], 2)
        self.assertEqual(DocumentCompletion.objects.filter(enrollment=enrollment_a).count(), 1)

        # Student B remains at 0%.
        progress_b = classroom_progress(actor=student_b, classroom_id=room.pk)
        self.assertEqual(progress_b['completed_activities'], 0)
        self.assertEqual(progress_b['percent'], 0.0)

        # Complete video and submit essay (pending grade still counts as completed).
        VideoProgress.objects.create(video=video, student=student_a, position=120, watched_until=120, completed_at=timezone.now())
        AssessmentAttempt.objects.filter(assessment=essay, student=student_a).update(status='SUBMITTED', submitted_at=timezone.now())
        refresh_classroom_progress(classroom_id=room.pk)

        enrollment_a.refresh_from_db()
        self.assertEqual(enrollment_a.status, Enrollment.Status.COMPLETED)
        self.assertEqual(enrollment_a.progress_percent, 100.0)
        first_completed_at = enrollment_a.completed_at
        self.assertIsNotNone(first_completed_at)

        # Re-refreshing preserves original completed_at.
        refresh_classroom_progress(classroom_id=room.pk)
        enrollment_a.refresh_from_db()
        self.assertEqual(enrollment_a.completed_at, first_completed_at)

        # Replacing published PDF version invalidates prior PDF completion and drops enrollment back to ACTIVE.
        v2 = DocumentVersion.objects.create(
            document=doc, version_number=2, file_name='doc_v2.pdf', file_size_bytes=120,
            checksum_sha256='1' * 64, page_count=6, original_storage_key='originals/doc_v2.pdf', status='EXTRACTED',
        )
        doc.active_version = v2
        doc.published_version = v2
        doc.save(update_fields=['active_version', 'published_version'])
        refresh_classroom_progress(classroom_id=room.pk)

        enrollment_a.refresh_from_db()
        self.assertEqual(enrollment_a.status, Enrollment.Status.ACTIVE)
        self.assertEqual(enrollment_a.progress_percent, 75.0)
        self.assertIsNone(enrollment_a.completed_at)

        # Removing the replaced PDF returns denominator to 3/3 = 100% COMPLETED.
        doc.removed_at = timezone.now()
        doc.is_published = False
        doc.published_version = None
        doc.save(update_fields=['removed_at', 'is_published', 'published_version'])
        refresh_classroom_progress(classroom_id=room.pk)

        enrollment_a.refresh_from_db()
        self.assertEqual(enrollment_a.status, Enrollment.Status.COMPLETED)
        self.assertEqual(enrollment_a.progress_percent, 100.0)
        self.assertIsNotNone(enrollment_a.completed_at)

    def test_withdrawn_enrollment_is_not_reopened_and_blocked(self):
        teacher, student_a, _, course, room, enrollment_a, _, session = _setup_classroom_fixture()
        _, v1 = _create_published_pdf(teacher, course, session)
        withdraw_classroom_enrollment(
            actor=teacher, course=course, classroom_id=room.pk, enrollment_id=enrollment_a.pk
        )
        refresh_classroom_progress(classroom_id=room.pk)
        enrollment_a.refresh_from_db()
        self.assertEqual(enrollment_a.status, Enrollment.Status.WITHDRAWN)

        with self.assertRaises(NotFound):
            classroom_progress(actor=student_a, classroom_id=room.pk)
        with self.assertRaises(NotFound):
            mark_document_complete(actor=student_a, classroom_id=room.pk, version_id=v1.pk)
        with self.assertRaises(PermissionDenied):
            mark_document_complete(actor=teacher, classroom_id=room.pk, version_id=v1.pk)

    def test_rebuild_classroom_progress_backfill_command(self):
        teacher, student_a, _, course, room, enrollment_a, _, session = _setup_classroom_fixture()
        _, v1 = _create_published_pdf(teacher, course, session)
        DocumentCompletion.objects.create(enrollment=enrollment_a, document_version=v1)
        Enrollment.objects.filter(pk=enrollment_a.pk).update(progress_percent=0, status=Enrollment.Status.ACTIVE, completed_at=None)
        call_command('rebuild_classroom_progress', classroom_id=str(room.pk))
        enrollment_a.refresh_from_db()
        self.assertEqual(enrollment_a.progress_percent, 100.0)
        self.assertEqual(enrollment_a.status, Enrollment.Status.COMPLETED)
        self.assertIsNotNone(enrollment_a.completed_at)


class LearningProgressConcurrencyTests(TransactionTestCase):
    def test_concurrent_duplicate_mark_complete_and_withdraw_race(self):
        teacher, student_a, _, course, room, enrollment_a, _, session = _setup_classroom_fixture()
        _, v1 = _create_published_pdf(teacher, course, session)

        def call_mark(_idx):
            try:
                return ('OK', mark_document_complete(actor=student_a, classroom_id=room.pk, version_id=v1.pk)['completed_activities'])
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(call_mark, [1, 2]))

        self.assertEqual(results, [('OK', 1), ('OK', 1)])
        self.assertEqual(DocumentCompletion.objects.filter(enrollment=enrollment_a, document_version=v1).count(), 1)

        # Concurrent mark vs withdraw never creates out-of-scope completion or reopens withdrawn enrollment.
        doc2, v2 = _create_published_pdf(teacher, course, session, title='PDF 2')

        def mark_v2(_):
            try:
                mark_document_complete(actor=student_a, classroom_id=room.pk, version_id=v2.pk)
                return 'MARKED'
            except NotFound:
                return 'BLOCKED'
            finally:
                connections.close_all()

        def withdraw(_):
            try:
                withdraw_classroom_enrollment(actor=teacher, course=course, classroom_id=room.pk, enrollment_id=enrollment_a.pk)
                return 'WITHDRAWN'
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(withdraw, None)
            f2 = pool.submit(mark_v2, None)
            out1, out2 = f1.result(), f2.result()

        self.assertEqual(out1, 'WITHDRAWN')
        self.assertIn(out2, {'MARKED', 'BLOCKED'})
        enrollment_a.refresh_from_db()
        self.assertEqual(enrollment_a.status, Enrollment.Status.WITHDRAWN)
