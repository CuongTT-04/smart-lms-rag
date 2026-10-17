import uuid
import tempfile
from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile
from django.test import TestCase
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient
from apps.users.models import User
from apps.courses.models import Classroom, ClassroomSession, CourseMember, Enrollment
from apps.courses.services import create_course, update_course
from common.testing import authenticate_client


class AssessmentTests(TestCase):
    def setUp(self):
        storage = tempfile.TemporaryDirectory()
        override = override_settings(ANNOUNCEMENTS_STORAGE_ROOT=storage.name)
        override.enable()
        self.addCleanup(storage.cleanup)
        self.addCleanup(override.disable)
        self.owner = User.objects.create_user('assessment-owner', role='TEACHER')
        self.student = User.objects.create_user('assessment-student', role='STUDENT', full_name='=SUM(A1)')
        self.other = User.objects.create_user('assessment-other', role='STUDENT')
        self.course = create_course(actor=self.owner, title='Course')
        update_course(actor=self.owner, course=self.course, changes={'status': 'PUBLISHED'})
        self.room = Classroom.objects.create(course=self.course, name='Room')
        CourseMember.objects.create(course=self.course, user=self.student, role='STUDENT')
        Enrollment.objects.create(classroom=self.room, student=self.student.student_profile)
        self.session = ClassroomSession.objects.create(classroom=self.room, is_draft=False)
        self.base = f'/api/courses/{self.course.pk}/classrooms/{self.room.pk}/sessions/{self.session.pk}/assessments/'
        self.teacher = authenticate_client(APIClient(), self.owner)
        self.learner = authenticate_client(APIClient(), self.student)

    def create(self, **changes):
        payload = {'title': 'Bài tập', 'kind': 'QUIZ', 'mode': 'PRACTICE', 'due_at': (timezone.now() + timedelta(days=1)).isoformat(),
                   'duration_seconds': 600, 'questions': [{'id': 'q1', 'prompt': 'Chọn A', 'choices': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}], 'correct_id': 'a', 'hint': 'Xem kiến thức A'}]}
        response = self.teacher.post(self.base, {**payload, **changes}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.detail = self.base + response.json()['id'] + '/'
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        return response.json()

    def start(self, **changes):
        response = self.learner.post(self.detail + 'start/', {'request_id': str(uuid.uuid4()), **changes}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.attempt = self.detail + f'attempts/{response.json()["id"]}/'
        return response.json()

    def save(self, revision=0, **changes):
        return self.learner.patch(self.attempt, {'revision': revision, **changes}, format='json')

    def submit(self, revision=1, **changes):
        return self.learner.post(self.attempt + 'submit/', {'revision': revision, 'confirmed': True, **changes}, format='json')

    def test_practice_repeat_keys_and_published_results(self):
        self.create()
        self.assertNotIn('correct_id', str(self.learner.get(self.detail).json()))
        self.start()
        self.assertEqual(self.save(answers={'q1': 'a'}).status_code, 200)
        result = self.submit()
        self.assertEqual(result.status_code, 200, result.content)
        self.assertIsNone(result.json()['score'])
        self.assertEqual(self.submit().json()['id'], result.json()['id'])
        self.teacher.patch(self.detail, {'results_published': True, 'solutions_published': True}, format='json')
        self.assertEqual(self.learner.get(self.attempt).json()['score'], 10)
        self.assertNotIn('correct_id', str(self.learner.get(self.detail).json()['questions']))
        self.assertIn('correct_id', str(self.learner.get(self.attempt).json()))
        second = self.start()
        self.assertEqual(second['number'], 2)
        self.assertEqual(self.learner.post(self.detail + 'assistance/', {}, format='json').status_code, 200)

    def test_test_mode_single_attempt_confirmation_and_warning_only(self):
        self.create(mode='TEST', kind='TEXT', questions=[])
        self.assertEqual(self.learner.post(self.detail + 'start/', {'request_id': str(uuid.uuid4())}, format='json').status_code, 400)
        attempt = self.start(fullscreen=True)
        self.assertEqual(self.save(text='Bài làm').status_code, 200)
        event = {'event_id': str(uuid.uuid4()), 'kind': 'TAB_HIDDEN'}
        self.assertEqual(self.learner.post(self.attempt + 'events/', event, format='json').status_code, 201)
        self.assertEqual(self.learner.post(self.attempt + 'events/', event, format='json').status_code, 201)
        self.assertEqual(self.learner.get(self.attempt).json()['status'], 'DRAFT')
        self.assertEqual(self.submit(confirmed=False).status_code, 400)
        self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(self.learner.post(self.detail + 'start/', {'request_id': str(uuid.uuid4()), 'fullscreen': True}, format='json').status_code, 400)
        self.assertEqual(self.learner.post(self.detail + 'assistance/', {}, format='json').status_code, 403)
        graded = self.teacher.patch(self.attempt + 'grade/', {'score': 7.5, 'feedback': 'Tốt', 'published': True, 'moderation_note': 'Đã xem log, giữ nguyên điểm.'}, format='json')
        self.assertEqual(graded.status_code, 200, graded.content)
        self.assertEqual(self.learner.get(self.attempt).json()['score'], 7.5)
        self.assertEqual(self.learner.get(self.attempt).json()['violation_count'], 1)
        self.teacher.patch(self.attempt + 'grade/', {'score': 8, 'feedback': 'Điều chỉnh', 'published': True}, format='json')
        detail = self.teacher.get(self.attempt).json()
        self.assertEqual(len(detail['grade_history']), 2)
        self.assertEqual(detail['moderation_note'], 'Đã xem log, giữ nguyên điểm.')
        self.assertEqual(attempt['status'], 'DRAFT')

    def test_expired_quiz_autosubmits_saved_answers_and_stale_save_rejected(self):
        from apps.courses.assessment_models import AssessmentAttempt
        self.create(mode='TEST')
        self.start(fullscreen=True)
        self.assertEqual(self.save(answers={'q1': 'a'}).status_code, 200)
        self.assertEqual(self.save(answers={'q1': 'b'}).status_code, 409)
        AssessmentAttempt.objects.filter(pk=self.attempt.rstrip('/').split('/')[-1]).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.learner.get(self.attempt)
        self.assertEqual(response.json()['status'], 'SUBMITTED')
        self.assertTrue(response.json()['auto_submitted'])
        self.assertEqual(response.json()['answers'], {'q1': 'a'})

    def test_permissions_immutability_and_export_filter(self):
        self.create()
        self.start()
        outsider = authenticate_client(APIClient(), self.other)
        self.assertEqual(outsider.get(self.attempt).status_code, 404)
        self.assertEqual(self.learner.get(self.detail + 'dashboard/').status_code, 404)
        self.assertEqual(self.learner.get(self.detail + 'export/').status_code, 404)
        self.assertEqual(self.teacher.patch(self.detail, {'mode': 'TEST'}, format='json').status_code, 400)
        self.save(answers={'q1': 'a'})
        self.submit()
        report = self.teacher.get(self.detail + 'dashboard/').json()
        self.assertEqual(report['summary']['submitted'], 1)
        self.assertEqual(report['question_stats'][0]['correct'], 1)
        response = self.teacher.get(self.detail + 'export/?q=does-not-exist')
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as book:
            self.assertNotIn('=SUM(A1)', book.read('xl/worksheets/sheet1.xml').decode())
        response = self.teacher.get(self.detail + 'export/')
        with ZipFile(BytesIO(response.content)) as book:
            xml = book.read('xl/worksheets/sheet1.xml').decode()
            self.assertIn('=SUM(A1)', xml)
            self.assertNotIn('<f>', xml)
        Enrollment.objects.filter(classroom=self.room).update(status='WITHDRAWN')
        self.assertEqual(self.learner.get(self.attempt).status_code, 404)

    def test_practice_text_resubmit_resets_grade_and_deadline_enforced(self):
        from apps.courses.assessment_models import Assessment
        self.create(kind='TEXT', questions=[])
        self.start()
        self.save(text='Bài lần đầu')
        self.submit()
        self.teacher.patch(self.attempt + 'grade/', {'score': 9, 'published': True}, format='json')
        second = self.start()
        self.assertIsNone(second['score'])
        self.assertEqual(second['text'], 'Bài lần đầu')
        self.save(text='Đã chỉnh sửa')
        Assessment.objects.filter(pk=self.detail.rstrip('/').split('/')[-1]).update(due_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.submit().status_code, 400)
        self.assertEqual(self.learner.get(self.attempt).json()['status'], 'DRAFT')

    def test_validation_rejects_incomplete_quiz_and_invalid_answers(self):
        response = self.teacher.post(self.base, {'title': 'Bad', 'kind': 'QUIZ', 'mode': 'TEST', 'due_at': (timezone.now()+timedelta(days=1)).isoformat(), 'questions': []}, format='json')
        self.assertEqual(response.status_code, 400)
        self.create()
        self.start()
        self.assertEqual(self.save(answers={'q1': 'foreign'}).status_code, 400)

    def test_mixed_single_multiple_questions_grade_exact_sets_and_export_all_choices(self):
        questions = [
            {'id':'q1','prompt':'Một đáp án','multiple':False,'choices':[{'id':'a','text':'A'},{'id':'b','text':'B'}],'correct_ids':['a']},
            {'id':'q2','prompt':'Nhiều đáp án','multiple':True,'choices':[{'id':'a','text':'Alpha'},{'id':'b','text':'Beta'},{'id':'c','text':'Gamma'}],'correct_ids':['a','b']},
            {'id':'q3','prompt':'Chọn nhiều nhưng chỉ một đáp án đúng','multiple':True,'choices':[{'id':'a','text':'A'},{'id':'b','text':'B'}],'correct_ids':['a']},
        ]
        self.create(questions=questions)
        student_questions = self.learner.get(self.detail).json()['questions']
        self.assertEqual([q['multiple'] for q in student_questions], [False, True, True])
        self.assertNotIn('correct_ids', str(student_questions))
        self.start()
        self.assertEqual(self.save(answers={'q1':['a','b']}).status_code,400)
        self.assertEqual(self.save(answers={'q2':['a','a']}).status_code,400)
        self.assertEqual(self.save(answers={'q1':'a','q2':['b','a'],'q3':['a']}).status_code,200)
        self.submit()
        self.teacher.patch(self.detail, {'results_published':True}, format='json')
        self.assertEqual(self.learner.get(self.attempt).json()['score'],10)
        report = self.teacher.get(self.detail+'dashboard/').json()
        self.assertEqual([q['correct'] for q in report['question_stats']],[1,1,1])
        response = self.teacher.get(self.detail+'export/')
        with ZipFile(BytesIO(response.content)) as book:
            xml = book.read('xl/worksheets/sheet2.xml').decode()
            self.assertIn('Alpha; Beta', xml)
        self.start()
        self.save(answers={'q1':'a','q2':['a'],'q3':['a']})
        self.submit()
        self.assertEqual(self.learner.get(self.attempt).json()['score'],6.67)

    def test_single_choice_question_rejects_multiple_answer_keys(self):
        payload = {'title':'Bad single','kind':'QUIZ','mode':'PRACTICE','due_at':(timezone.now()+timedelta(days=1)).isoformat(),
            'questions':[{'id':'q1','prompt':'Chọn','multiple':False,'choices':[{'id':'a','text':'A'},{'id':'b','text':'B'}],'correct_ids':['a','b']}]}
        self.assertEqual(self.teacher.post(self.base,payload,format='json').status_code,400)

    def test_replacing_draft_file_cleans_unreferenced_source_but_keeps_submitted_history(self):
        from apps.courses.assessment_models import AssessmentAttempt
        self.create(kind='TEXT', questions=[])
        self.start()
        def upload(revision, name):
            return self.learner.patch(self.attempt, {'revision': revision, 'file': SimpleUploadedFile(name, b'%PDF-1.7\n%%EOF', content_type='application/pdf')}, format='multipart')
        first = upload(0, 'first.pdf')
        self.assertEqual(first.status_code, 200, first.content)
        attempt = AssessmentAttempt.objects.get(pk=self.attempt.rstrip('/').split('/')[-1])
        storage = attempt.file.storage
        old_key = attempt.file.name
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(upload(1, 'second.pdf').status_code, 200)
        self.assertFalse(storage.exists(old_key))
        attempt.refresh_from_db()
        submitted_key = attempt.file.name
        self.submit(revision=2)
        self.start()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(upload(0, 'third.pdf').status_code, 200)
        self.assertTrue(storage.exists(submitted_key))
        attempt = AssessmentAttempt.objects.get(pk=self.attempt.rstrip('/').split('/')[-1])
        removed_key = attempt.file.name
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.save(revision=1, remove_file=True).status_code, 200)
        self.assertFalse(storage.exists(removed_key))

    def test_file_signature_grade_bounds_and_student_file_privacy(self):
        self.create(kind='TEXT', questions=[])
        self.start()
        bad = self.learner.patch(self.attempt, {'revision': 0, 'file': SimpleUploadedFile('bad.png', b'not-a-png')}, format='multipart')
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.save(text='Text answer').status_code, 200)
        self.submit()
        self.assertEqual(self.teacher.patch(self.attempt+'grade/', {'score': 11}, format='json').status_code, 400)
        outsider = authenticate_client(APIClient(), self.other)
        self.assertEqual(outsider.get(self.attempt+'file/').status_code, 404)
