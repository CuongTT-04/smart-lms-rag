from datetime import timedelta
from io import BytesIO
import uuid
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.assessment_models import Assessment, AssessmentAttempt
from apps.courses.enrollment_services import join_by_code, withdraw_classroom_enrollment
from apps.courses.models import Classroom, ClassroomSession
from apps.courses.services import create_course, update_course
from apps.users.models import User
from common.testing import authenticate_client


class ClassroomResultsTests(TestCase):
    def test_results_and_export_expire_quiz_drafts_without_publishing_scores(self):
        from apps.courses.models import Enrollment
        for export in (False, True):
            with self.subTest(export=export):
                room = Classroom.objects.create(course=self.course, name='Expired quiz')
                _, enrollment, _ = join_by_code(actor=self.student1, class_code=room.class_code)
                session = ClassroomSession.objects.create(classroom=room, title='Quiz', is_draft=False)
                assessment = Assessment.objects.create(session=session, title='Quiz hết giờ', kind='QUIZ',
                    mode='TEST', is_published=True, due_at=timezone.now() + timedelta(days=1),
                    questions=[{'id': 'q1', 'prompt': '?', 'choices': [{'id': 'a', 'text': 'A'}], 'correct_ids': ['a']}])
                attempt = AssessmentAttempt.objects.create(assessment=assessment, student=self.student1,
                    number=1, request_id=uuid.uuid4(), answers={'q1': 'a'},
                    expires_at=timezone.now() - timedelta(minutes=1))
                url = f'/api/courses/{self.course.pk}/classrooms/{room.pk}/results/'
                response = self.teacher_client.get(url + ('export/' if export else ''))
                self.assertEqual(response.status_code, 200)
                if not export:
                    self.assertEqual(response.json()['results'][0]['enrollment_status'], 'COMPLETED')
                attempt.refresh_from_db()
                self.assertEqual(attempt.status, 'SUBMITTED')
                self.assertTrue(attempt.auto_submitted)
                self.assertEqual(attempt.score, 10)
                enrollment.refresh_from_db()
                self.assertEqual(enrollment.status, Enrollment.Status.COMPLETED)
                self.assertEqual(enrollment.progress_percent, 100)
                first_submitted = attempt.submitted_at
                body = self.teacher_client.get(url).json()
                self.assertEqual(body['results'][0]['enrollment_status'], 'COMPLETED')
                self.assertEqual(body['results'][0]['assessments'][0]['score'], 10)
                attempt.refresh_from_db()
                self.assertEqual(attempt.submitted_at, first_submitted)
                student = self.s1_client.get(url).json()['results'][0]['assessments'][0]
                self.assertEqual(student['submission_status'], 'SUBMITTED')
                self.assertIsNone(student['score'])

    def test_student_result_view_does_not_expire_another_students_attempt(self):
        join_by_code(actor=self.student1, class_code=self.room.class_code)
        join_by_code(actor=self.student2, class_code=self.room.class_code)
        session = ClassroomSession.objects.create(classroom=self.room, title='Quiz', is_draft=False)
        assessment = Assessment.objects.create(session=session, title='Quiz', kind='QUIZ', mode='TEST',
            is_published=True, due_at=timezone.now() + timedelta(days=1),
            questions=[{'id': 'q1', 'prompt': '?', 'choices': [{'id': 'a', 'text': 'A'}], 'correct_ids': ['a']}])
        attempts = [AssessmentAttempt.objects.create(assessment=assessment, student=student,
            number=1, request_id=uuid.uuid4(), expires_at=timezone.now() - timedelta(minutes=1))
            for student in (self.student1, self.student2)]
        self.assertEqual(self.s1_client.get(self.url).status_code, 200)
        for attempt in attempts:
            attempt.refresh_from_db()
        self.assertEqual(attempts[0].status, 'SUBMITTED')
        self.assertEqual(attempts[0].score, 0)
        self.assertEqual(attempts[1].status, 'DRAFT')

    def setUp(self):
        self.teacher = User.objects.create_user('res-teacher', full_name='Cô Lan', role='TEACHER')
        self.other_teacher = User.objects.create_user('res-other-teacher', role='TEACHER')
        self.student1 = User.objects.create_user('res-s1', full_name='=SUM(A1:A2)', role='STUDENT')
        self.student2 = User.objects.create_user('res-s2', full_name='Bình An', role='STUDENT')
        self.outsider = User.objects.create_user('res-outsider', role='STUDENT')

        self.course = create_course(actor=self.teacher, title='Mạng máy tính')
        update_course(actor=self.teacher, course=self.course, changes={'status': 'PUBLISHED'})
        self.room = Classroom.objects.create(course=self.course, name='Lớp A')
        self.other_room = Classroom.objects.create(course=self.course, name='Lớp B')

        self.teacher_client = authenticate_client(APIClient(), self.teacher)
        self.s1_client = authenticate_client(APIClient(), self.student1)
        self.s2_client = authenticate_client(APIClient(), self.student2)
        self.outsider_client = authenticate_client(APIClient(), self.outsider)

        self.url = f'/api/courses/{self.course.pk}/classrooms/{self.room.pk}/results/'
        self.export_url = f'{self.url}export/'

    def test_empty_classroom_results(self):
        res = self.teacher_client.get(self.url)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['results'], [])
        self.assertEqual(body['assessments'], [])
        self.assertEqual(body['summary']['student_count'], 0)
        self.assertIsNone(body['summary']['average_score'])

    def test_practice_best_score_visibility_zero_pending_overdue_removed_and_filters(self):
        join_by_code(actor=self.student1, class_code=self.room.class_code)
        _, e2, _ = join_by_code(actor=self.student2, class_code=self.room.class_code)
        session = ClassroomSession.objects.create(classroom=self.room, title='Buổi 1', is_draft=False)

        practice = Assessment.objects.create(
            session=session,
            title='Ôn tập 1',
            kind='QUIZ',
            mode='PRACTICE',
            questions=[{'id': 'q1', 'prompt': '?', 'choices': [{'id': 'a', 'text': 'A'}], 'correct_ids': ['a']}],
            due_at=timezone.now() + timedelta(days=2),
            is_published=True,
            results_published=False,
        )
        overdue_test = Assessment.objects.create(
            session=session,
            title='Kiểm tra quá hạn',
            kind='TEXT',
            mode='TEST',
            due_at=timezone.now() - timedelta(hours=2),
            is_published=True,
        )
        removed_quiz = Assessment.objects.create(
            session=session,
            title='Bài đã gỡ',
            kind='QUIZ',
            mode='PRACTICE',
            due_at=timezone.now() + timedelta(days=1),
            is_published=False,
            removed_at=timezone.now(),
        )

        # Student 1: 4.0 (published), 8.0 (unpublished), 0.0 (published), pending (None), and a DRAFT on test.
        AssessmentAttempt.objects.create(
            assessment=practice, student=self.student1, request_id=uuid.uuid4(), number=1,
            status='SUBMITTED', submitted_at=timezone.now() - timedelta(minutes=30),
            score=4, grade_published=True, expires_at=timezone.now() + timedelta(days=1),
        )
        AssessmentAttempt.objects.create(
            assessment=practice, student=self.student1, request_id=uuid.uuid4(), number=2,
            status='SUBMITTED', submitted_at=timezone.now() - timedelta(minutes=20),
            score=8, grade_published=False, expires_at=timezone.now() + timedelta(days=1),
        )
        AssessmentAttempt.objects.create(
            assessment=practice, student=self.student1, request_id=uuid.uuid4(), number=3,
            status='SUBMITTED', submitted_at=timezone.now() - timedelta(minutes=10),
            score=0, grade_published=True, expires_at=timezone.now() + timedelta(days=1),
        )
        AssessmentAttempt.objects.create(
            assessment=practice, student=self.student1, request_id=uuid.uuid4(), number=4,
            status='SUBMITTED', submitted_at=timezone.now() - timedelta(minutes=5),
            score=None, grade_published=False, expires_at=timezone.now() + timedelta(days=1),
        )
        AssessmentAttempt.objects.create(
            assessment=overdue_test, student=self.student1, request_id=uuid.uuid4(), number=1,
            status='DRAFT', expires_at=timezone.now() + timedelta(days=1),
        )
        AssessmentAttempt.objects.create(
            assessment=removed_quiz, student=self.student1, request_id=uuid.uuid4(), number=1,
            status='SUBMITTED', submitted_at=timezone.now(), score=6, grade_published=True,
            expires_at=timezone.now() + timedelta(days=1),
        )

        # Student 2: single 0.0 on practice (published), submitted pending on test.
        AssessmentAttempt.objects.create(
            assessment=practice, student=self.student2, request_id=uuid.uuid4(), number=1,
            status='SUBMITTED', submitted_at=timezone.now(), score=0, grade_published=True,
            expires_at=timezone.now() + timedelta(days=1),
        )
        AssessmentAttempt.objects.create(
            assessment=overdue_test, student=self.student2, request_id=uuid.uuid4(), number=1,
            status='SUBMITTED', submitted_at=timezone.now(), score=None, grade_published=False,
            expires_at=timezone.now() + timedelta(days=1),
        )

        # Teacher view sees 8.0 for student 1, 0.0 for student 2, and draft does NOT count as submitted.
        teacher_res = self.teacher_client.get(self.url)
        self.assertEqual(teacher_res.status_code, 200)
        tdata = teacher_res.json()
        self.assertEqual(tdata['viewer_role'], 'TEACHER')
        self.assertEqual(tdata['summary']['student_count'], 2)
        self.assertEqual(tdata['summary']['active_assessment_count'], 2)
        self.assertEqual(tdata['summary']['removed_assessment_count'], 1)
        self.assertEqual(tdata['summary']['submitted_cells'], 3)  # s1: practice; s2: practice + test
        self.assertEqual(tdata['summary']['draft_cells'], 1)  # s1: draft test
        self.assertEqual(tdata['summary']['not_submitted_cells'], 0)
        self.assertEqual(tdata['summary']['pending_grading_cells'], 2)  # s1 practice (+1 pending) + s2 test pending
        self.assertEqual(tdata['summary']['pending_attempts'], 2)

        rows_by_name = {r['name']: r for r in tdata['results']}
        s1_row = rows_by_name['=SUM(A1:A2)']
        self.assertEqual(s1_row['submitted_count'], 1)
        self.assertEqual(s1_row['draft_count'], 1)
        self.assertEqual(s1_row['overdue_count'], 1)
        self.assertEqual(s1_row['pending_grading_count'], 1)
        self.assertEqual(s1_row['pending_attempts_count'], 1)
        s1_cells = {c['assessment_id']: c for c in s1_row['assessments']}
        self.assertEqual(s1_cells[str(practice.pk)]['score'], 8.0)
        self.assertEqual(s1_cells[str(practice.pk)]['pending_attempts_count'], 1)
        self.assertTrue(s1_cells[str(practice.pk)]['has_pending_grading'])
        self.assertEqual(s1_cells[str(overdue_test.pk)]['submission_status'], 'DRAFT')
        self.assertTrue(s1_cells[str(overdue_test.pk)]['is_overdue'])
        self.assertTrue(s1_cells[str(removed_quiz.pk)]['is_removed'])

        s2_row = rows_by_name['Bình An']
        self.assertEqual(s2_row['average_score'], 0.0)
        s2_cells = {c['assessment_id']: c for c in s2_row['assessments']}
        self.assertEqual(s2_cells[str(practice.pk)]['score'], 0.0)
        self.assertEqual(s2_cells[str(practice.pk)]['grading_status'], 'GRADED')
        self.assertIsNone(s2_cells[str(overdue_test.pk)]['score'])
        self.assertEqual(s2_cells[str(overdue_test.pk)]['grading_status'], 'PENDING')

        # Student 1 view must NOT see unpublished 8.0; sees 4.0 instead and only 1 row.
        s1_res = self.s1_client.get(self.url)
        self.assertEqual(s1_res.status_code, 200)
        s1_data = s1_res.json()
        self.assertEqual(len(s1_data['results']), 1)
        self.assertEqual(s1_data['results'][0]['student_id'], str(self.student1.pk))
        s1_view_cells = {c['assessment_id']: c for c in s1_data['results'][0]['assessments']}
        self.assertEqual(s1_view_cells[str(practice.pk)]['score'], 4.0)
        self.assertEqual(s1_view_cells[str(practice.pk)]['pending_attempts_count'], 2)
        self.assertEqual(s1_data['results'][0]['pending_grading_count'], 1)
        self.assertEqual(s1_data['results'][0]['pending_attempts_count'], 2)

        # Student cannot query another student's ID; invalid filters rejected.
        self.assertEqual(self.s1_client.get(f'{self.url}?student_id={self.student2.pk}').status_code, 400)
        self.assertEqual(self.teacher_client.get(f'{self.url}?submission_status=BAD').status_code, 400)

        # Filter by grading_status=PENDING -> both student 1 (has +1 ungraded attempt on practice) and student 2 match.
        filtered = self.teacher_client.get(f'{self.url}?grading_status=PENDING')
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()['summary']['student_count'], 2)
        self.assertEqual(filtered.json()['summary']['pending_grading_cells'], 2)
        self.assertEqual(filtered.json()['summary']['pending_attempts'], 2)
        filtered_by_id = {r['student_id']: r for r in filtered.json()['results']}
        self.assertEqual(filtered_by_id[str(self.student1.pk)]['assessments'][0]['score'], 8.0)

        # Permissions & export checks.
        self.assertEqual(APIClient().get(self.url).status_code, 401)
        self.assertEqual(self.outsider_client.get(self.url).status_code, 404)
        self.assertEqual(authenticate_client(APIClient(), self.other_teacher).get(self.url).status_code, 404)
        self.assertEqual(self.s1_client.get(self.export_url).status_code, 403)
        self.assertEqual(self.outsider_client.get(self.export_url).status_code, 404)

        export = self.teacher_client.get(f'{self.export_url}?q=SUM')
        self.assertEqual(export.status_code, 200)
        with ZipFile(BytesIO(export.content)) as book:
            sheet_xml = book.read('xl/worksheets/sheet1.xml').decode('utf-8')
            self.assertNotIn('<f', sheet_xml)
            self.assertIn('=SUM(A1:A2)', sheet_xml)
            root = ET.fromstring(sheet_xml)
            texts = [el.text for el in root.iter() if el.tag.endswith('}t') and el.text]
            self.assertIn('=SUM(A1:A2)', texts)

        # Withdrawn student loses access to results.
        withdraw_classroom_enrollment(actor=self.teacher, course=self.course, classroom_id=self.room.pk, enrollment_id=e2.pk)
        self.assertEqual(self.s2_client.get(self.url).status_code, 404)

    def test_query_count_does_not_scale_with_student_count(self):
        room_small = Classroom.objects.create(course=self.course, name='Lớp nhỏ')
        room_large = Classroom.objects.create(course=self.course, name='Lớp lớn')
        for room, n in [(room_small, 3), (room_large, 30)]:
            session = ClassroomSession.objects.create(classroom=room, title='Buổi 1', is_draft=False)
            quiz = Assessment.objects.create(
                session=session, title='Quiz', kind='QUIZ', mode='PRACTICE',
                questions=[{'id': 'q1', 'prompt': '?', 'choices': [{'id': 'a', 'text': 'A'}], 'correct_ids': ['a']}],
                due_at=timezone.now() + timedelta(days=1), is_published=True,
            )
            for i in range(n):
                student = User.objects.create_user(f'qc-{room.pk.hex[:4]}-{i}', role='STUDENT')
                join_by_code(actor=student, class_code=room.class_code)
                AssessmentAttempt.objects.create(
                    assessment=quiz, student=student, request_id=uuid.uuid4(), number=1,
                    status='SUBMITTED', submitted_at=timezone.now(), score=8,
                    expires_at=timezone.now() + timedelta(days=1),
                )

        with CaptureQueriesContext(connection) as ctx_small:
            res_small = self.teacher_client.get(f'/api/courses/{self.course.pk}/classrooms/{room_small.pk}/results/')
            self.assertEqual(res_small.status_code, 200)

        with CaptureQueriesContext(connection) as ctx_large:
            res_large = self.teacher_client.get(f'/api/courses/{self.course.pk}/classrooms/{room_large.pk}/results/')
            self.assertEqual(res_large.status_code, 200)

        self.assertEqual(len(ctx_small), len(ctx_large))
