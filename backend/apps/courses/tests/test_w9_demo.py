from io import BytesIO, StringIO
import os
import tempfile
from unittest.mock import patch

import cv2
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import TestCase, override_settings
from pypdf import PdfReader
from rest_framework.test import APIClient

from apps.courses.assessment_models import Assessment, AssessmentAttempt
from apps.courses.management.commands.seed_w9_demo import DEMO_VIDEO_CHECKPOINT, DEMO_VIDEO_DURATION, demo_uuid
from apps.courses.models import Classroom, Course, Enrollment
from apps.courses.progress_models import DocumentCompletion
from apps.courses.video_models import SessionVideo, VideoProgress
from apps.documents.models import DocumentVersion
from apps.documents.storage import private_path
from apps.users.models import User
from common.testing import authenticate_client, close_response


class W9DemoSeedTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.override = override_settings(
            DOCUMENTS_STORAGE_ROOT=os.path.join(self.temp_dir.name, 'docs'),
            ANNOUNCEMENTS_STORAGE_ROOT=os.path.join(self.temp_dir.name, 'ann'),
        )
        self.override.enable()
        self.addCleanup(self.override.disable)

    def _run_seed(self, *, db_name='w9_demo_test', enabled='1', password='DemoOnlyPassword!99', anchor='2026-11-18T10:00:00Z'):
        out = StringIO()
        env = {'W9_DEMO_ENABLED': enabled, 'W9_DEMO_PASSWORD': password}
        old_name = connections['default'].settings_dict['NAME']
        connections['default'].settings_dict['NAME'] = db_name
        try:
            with patch.dict(os.environ, env, clear=False):
                call_command('seed_w9_demo', anchor=anchor, stdout=out)
        finally:
            connections['default'].settings_dict['NAME'] = old_name
        return out.getvalue()

    def test_seed_refuses_without_opt_in_or_demo_db_prefix_or_password(self):
        with self.assertRaises(CommandError):
            self._run_seed(enabled='0')
        with self.assertRaises(CommandError):
            self._run_seed(db_name='smart_lms')
        with self.assertRaises(CommandError):
            self._run_seed(password='short')

    def test_seed_creates_valid_playable_media_is_idempotent_and_detects_conflicts(self):
        pw = 'DemoOnlyPassword!99'
        output = self._run_seed(password=pw)
        self.assertNotIn(pw, output)
        self.assertIn('W9 demo seed ready', output)

        counts_first = (
            User.objects.count(),
            Course.objects.count(),
            Classroom.objects.count(),
            Enrollment.objects.count(),
            Assessment.objects.count(),
            AssessmentAttempt.objects.count(),
            DocumentCompletion.objects.count(),
        )

        # Second run does not increase counts.
        self._run_seed(password=pw)
        counts_second = (
            User.objects.count(),
            Course.objects.count(),
            Classroom.objects.count(),
            Enrollment.objects.count(),
            Assessment.objects.count(),
            AssessmentAttempt.objects.count(),
            DocumentCompletion.objects.count(),
        )
        self.assertEqual(counts_first, counts_second)

        course1_id = demo_uuid('w9demo:course:1')
        room1_id = demo_uuid('w9demo:room:1')
        room2_id = demo_uuid('w9demo:room:2')
        session1_id = demo_uuid('w9demo:session:1')
        doc1_id = demo_uuid('w9demo:doc:1')
        ver1_id = demo_uuid('w9demo:doc:1:v1')
        video1_id = demo_uuid('w9demo:video:1')

        t1 = User.objects.get(username='w9demo_t1')
        t2 = User.objects.get(username='w9demo_t2')
        s1 = User.objects.get(username='w9demo_s1')
        s2 = User.objects.get(username='w9demo_s2')
        s3 = User.objects.get(username='w9demo_s3')

        t1_client = authenticate_client(APIClient(), t1)
        t2_client = authenticate_client(APIClient(), t2)
        s1_client = authenticate_client(APIClient(), s1)
        s2_client = authenticate_client(APIClient(), s2)
        s3_client = authenticate_client(APIClient(), s3)

        # Verify PDF original and protected view API return real readable 2-page PDFs.
        ver1 = DocumentVersion.objects.get(pk=ver1_id)
        original_reader = PdfReader(private_path(ver1.original_storage_key))
        self.assertEqual(len(original_reader.pages), 2)
        self.assertIn('Trang 1', original_reader.pages[0].extract_text())

        view_res = s1_client.get(f'/api/documents/{doc1_id}/view/')
        self.assertEqual(view_res.status_code, 200)
        view_reader = PdfReader(BytesIO(view_res.content))
        self.assertEqual(len(view_reader.pages), 2)
        self.assertIn(s1.email, view_reader.pages[0].extract_text())

        # Verify WebM video file is real, readable with OpenCV, and matches duration > checkpoint.
        video1 = SessionVideo.objects.get(pk=video1_id)
        self.assertEqual(video1.duration, DEMO_VIDEO_DURATION)
        self.assertGreater(video1.duration, DEMO_VIDEO_CHECKPOINT)
        video_res = s1_client.get(
            f'/api/courses/{course1_id}/classrooms/{room1_id}/sessions/{session1_id}/videos/{video1_id}/file/'
        )
        self.assertEqual(video_res.status_code, 200)
        self.assertEqual(video_res['Content-Type'], 'video/webm')
        close_response(video_res)

        with video1.file.open('rb') as stream:
            video_bytes = stream.read()
        self.assertTrue(video_bytes.startswith(b'\x1aE\xdf\xa3'))
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name
        try:
            cap = cv2.VideoCapture(tmp_path)
            frames = 0
            while True:
                ok, _ = cap.read()
                if not ok:
                    break
                frames += 1
            cap.release()
            self.assertEqual(frames, int(DEMO_VIDEO_DURATION))
        finally:
            os.unlink(tmp_path)

        # Verify expected API numbers per role.
        r1_results = t1_client.get(f'/api/courses/{course1_id}/classrooms/{room1_id}/results/').json()
        self.assertEqual(r1_results['summary']['student_count'], 2)
        self.assertEqual(r1_results['summary']['active_assessment_count'], 2)
        by_user = {row['username']: row for row in r1_results['results']}
        self.assertEqual(by_user['w9demo_s1']['progress']['percent'], 50.0)
        self.assertEqual(by_user['w9demo_s1']['progress']['completed_activities'], 2)
        self.assertEqual(by_user['w9demo_s1']['progress']['total_activities'], 4)
        self.assertEqual(by_user['w9demo_s1']['average_score'], 0.0)
        self.assertEqual(by_user['w9demo_s1']['draft_count'], 1)

        self.assertEqual(by_user['w9demo_s2']['progress']['percent'], 100.0)
        self.assertIsNotNone(by_user['w9demo_s2']['progress']['completed_at'])
        self.assertEqual(by_user['w9demo_s2']['average_score'], 10.0)
        self.assertEqual(by_user['w9demo_s2']['pending_grading_count'], 1)

        s1_prog = s1_client.get(f'/api/courses/{course1_id}/classrooms/{room1_id}/progress/').json()
        self.assertEqual(s1_prog['completed_activities'], 2)
        self.assertEqual(s1_prog['total_activities'], 4)
        self.assertEqual(s1_prog['percent'], 50.0)

        s2_r2 = s2_client.get(f'/api/courses/{course1_id}/classrooms/{room2_id}/results/').json()
        cells = {c['title']: c for c in s2_r2['results'][0]['assessments']}
        self.assertIsNone(cells['W9 Demo - Quiz kiểm tra']['score'])
        self.assertEqual(cells['W9 Demo - Quiz kiểm tra']['grading_status'], 'PENDING')
        self.assertTrue(cells['W9 Demo - Bài quá hạn']['is_overdue'])

        self.assertEqual(s3_client.get(f'/api/courses/{course1_id}/classrooms/{room1_id}/progress/').status_code, 404)
        self.assertEqual(s3_client.get(f'/api/courses/{course1_id}/classrooms/{room1_id}/results/').status_code, 404)
        self.assertEqual(t2_client.get(f'/api/courses/{course1_id}/classrooms/{room1_id}/results/').status_code, 404)

        # Conflict checks: altered attempt score/status must raise CommandError and not overwrite.
        req_s1_q1 = demo_uuid('w9demo:attempt:s1:q1')
        AssessmentAttempt.objects.filter(request_id=req_s1_q1).update(score=9)
        with self.assertRaises(CommandError):
            self._run_seed(password=pw)
        AssessmentAttempt.objects.filter(request_id=req_s1_q1).update(score=0)

        # Conflict check: incomplete VideoProgress must raise CommandError and NOT auto-mark completed.
        vp = VideoProgress.objects.get(video=video1, student=s2)
        original_completed_at = vp.completed_at
        VideoProgress.objects.filter(pk=vp.pk).update(completed_at=None)
        with self.assertRaises(CommandError):
            self._run_seed(password=pw)
        vp.refresh_from_db()
        self.assertIsNone(vp.completed_at)
        VideoProgress.objects.filter(pk=vp.pk).update(completed_at=original_completed_at)

        # Conflict check: deleted VideoProgress on re-run must raise CommandError and NOT recreate as completed.
        saved_vp_fields = dict(
            position=vp.position,
            watched_until=vp.watched_until,
            completed_at=vp.completed_at,
            passed=vp.passed,
        )
        vp.delete()
        with self.assertRaises(CommandError):
            self._run_seed(password=pw)
        self.assertFalse(VideoProgress.objects.filter(video=video1, student=s2).exists())
        VideoProgress.objects.create(video=video1, student=s2, **saved_vp_fields)

        # Conflict check: S3 reactivated must raise CommandError instead of silently withdrawing.
        Enrollment.objects.filter(classroom_id=room1_id, student=s3.student_profile).update(status='ACTIVE')
        with self.assertRaises(CommandError):
            self._run_seed(password=pw)
        Enrollment.objects.filter(classroom_id=room1_id, student=s3.student_profile).update(status='WITHDRAWN')

        # Conflict check: altered user role must raise CommandError.
        User.objects.filter(username='w9demo_s1').update(role='TEACHER')
        with self.assertRaises(CommandError):
            self._run_seed(password=pw)
