import tempfile
from datetime import timedelta
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from apps.users.models import User
from apps.courses.models import Classroom, ClassroomSession, CourseMember, Enrollment
from apps.courses.services import create_course, update_course
from common.testing import authenticate_client


class SessionVideoTests(TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(ANNOUNCEMENTS_STORAGE_ROOT=self.storage.name)
        self.settings_override.enable()
        self.addCleanup(self.storage.cleanup)
        self.addCleanup(self.settings_override.disable)
        self.owner = User.objects.create_user('video-owner', role='TEACHER')
        self.student = User.objects.create_user('video-student', role='STUDENT')
        self.other = User.objects.create_user('video-other', role='STUDENT')
        self.course = create_course(actor=self.owner, title='Video course')
        update_course(actor=self.owner, course=self.course, changes={'status': 'PUBLISHED'})
        self.room = Classroom.objects.create(course=self.course, name='Room')
        CourseMember.objects.create(course=self.course, user=self.student, role='STUDENT')
        Enrollment.objects.create(classroom=self.room, student=self.student.student_profile)
        self.session = ClassroomSession.objects.create(classroom=self.room, is_draft=False)
        self.url = f'/api/courses/{self.course.pk}/classrooms/{self.room.pk}/sessions/{self.session.pk}/videos/'
        self.teacher = authenticate_client(APIClient(), self.owner)
        self.learner = authenticate_client(APIClient(), self.student)

    def upload(self):
        source = SimpleUploadedFile('lesson.mp4', b'\x00\x00\x00\x18ftypmp42' + b'0' * 40, content_type='video/mp4')
        response = self.teacher.post(self.url, {'title': 'Bài giảng', 'duration': 60, 'file': source})
        self.assertEqual(response.status_code, 201, response.content)
        self.detail = self.url + response.json()['id'] + '/'
        return response.json()

    def question(self, **changes):
        values = {'kind': 'MCQ', 'prompt': 'Chọn đúng', 'start_time': 10, 'rewind_time': 2,
                  'choices': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}, {'id': 'c', 'text': 'C'}], 'correct_ids': ['a', 'b'], 'hint': 'Gợi ý'}
        response = self.teacher.post(self.detail + 'questions/', {**values, **changes}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def advance(self, position):
        from apps.courses.video_models import VideoProgress
        VideoProgress.objects.filter(video_id=self.detail.rstrip('/').split('/')[-1]).update(updated_at=timezone.now() - timedelta(seconds=10))
        return self.learner.put(self.detail + 'progress/', {'position': position}, format='json')

    def test_explicit_multiple_type_persists_even_with_one_correct_option(self):
        self.upload()
        q = self.question(multiple=True,correct_ids=['a'],start_time=0,rewind_time=None)
        self.assertTrue(q['multiple'])
        self.teacher.patch(self.detail,{'is_published':True},format='json')
        viewed = self.learner.get(self.detail).json()['questions'][0]
        self.assertTrue(viewed['multiple'])
        self.assertNotIn('correct_ids',viewed)
        answer = self.answer(q,selected_ids=['a'])
        self.assertEqual(answer.status_code,200,answer.content)
        self.assertTrue(answer.json()['snapshot']['multiple'])
        changed = self.teacher.patch(self.detail+f'questions/{q["id"]}/',{'multiple':False,'correct_ids':['a','b']},format='json')
        self.assertEqual(changed.status_code,400)

    def answer(self, question, **values):
        import uuid
        return self.learner.post(self.detail + f'questions/{question["id"]}/answers/', {'request_id': str(uuid.uuid4()), 'revision': question['revision'], **values}, format='json')

    def test_private_upload_publication_and_answer_keys(self):
        self.upload()
        question = self.question()
        self.assertEqual(self.learner.get(self.url).json()['results'], [])
        self.assertEqual(self.learner.get(self.detail).status_code, 404)
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        response = self.learner.get(self.detail)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('correct_ids', response.json()['questions'][0])
        self.assertEqual(question['correct_ids'], ['a', 'b'])
        self.assertEqual(self.learner.get(self.detail + 'file/').status_code, 200)
        outsider = authenticate_client(APIClient(), self.other)
        self.assertEqual(outsider.get(self.detail + 'file/').status_code, 404)
        self.assertEqual(self.learner.post(self.detail + 'questions/', {}, format='json').status_code, 404)
        self.assertEqual(self.learner.get(self.detail + 'responses/').status_code, 404)
        self.teacher.patch(self.detail, {'is_published': False}, format='json')
        self.assertEqual(self.learner.get(self.detail + 'file/').status_code, 404)

    def test_forward_jump_early_answer_and_multiple_choice_rewind(self):
        self.upload()
        question = self.question()
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        self.learner.get(self.detail)
        self.assertEqual(self.advance(50).status_code, 400)
        self.assertEqual(self.answer(question, selected_ids=['a', 'b']).status_code, 400)
        self.assertEqual(self.advance(5).status_code, 200)
        self.assertEqual(self.advance(10).status_code, 200)
        wrong = self.answer(question, selected_ids=['a'])
        self.assertEqual(wrong.status_code, 200)
        self.assertFalse(wrong.json()['is_correct'])
        self.assertEqual(wrong.json()['rewind_to'], 2)
        self.assertEqual(self.learner.get(self.detail).json()['progress']['position'], 2)
        self.assertEqual(self.answer(question, selected_ids=['a', 'b']).status_code, 400)
        self.advance(7)
        self.advance(10)
        self.assertTrue(self.answer(question, selected_ids=['b', 'a']).json()['is_correct'])
        self.assertIn(question['id'], self.learner.get(self.detail).json()['progress']['passed_ids'])

    def test_text_submission_unlocks_without_grading_and_counts_distinct_students(self):
        self.upload()
        question = self.question(kind='TEXT', choices=[], correct_ids=[], rewind_time=None, start_time=0)
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        self.learner.get(self.detail)
        import uuid
        request_id = str(uuid.uuid4())
        payload = {'revision': 1, 'request_id': request_id, 'text': 'Câu trả lời tự luận'}
        path = self.detail + f'questions/{question["id"]}/answers/'
        first = self.learner.post(path, payload, format='json')
        second = self.learner.post(path, payload, format='json')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertIsNone(first.json()['is_correct'])
        self.assertIn(question['id'], self.learner.get(self.detail).json()['progress']['passed_ids'])
        report = self.teacher.get(self.detail + 'responses/').json()
        self.assertEqual(report['questions'][0]['answered_students'], 1)
        self.assertEqual(report['count'], 1)
        self.assertEqual(report['results'][0]['text'], 'Câu trả lời tự luận')

    def test_question_rules_and_edits_invalidate_old_completion(self):
        self.upload()
        invalid = {'kind': 'TEXT', 'prompt': 'Text', 'start_time': 3, 'rewind_time': 1}
        self.assertEqual(self.teacher.post(self.detail + 'questions/', invalid, format='json').status_code, 400)
        question = self.question(start_time=0, rewind_time=None)
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        self.learner.get(self.detail)
        self.assertTrue(self.answer(question, selected_ids=['a', 'b']).json()['is_correct'])
        updated = self.teacher.patch(self.detail + f'questions/{question["id"]}/', {'prompt': 'Đề sửa'}, format='json')
        self.assertEqual(updated.json()['revision'], 2)
        self.assertNotIn(question['id'], self.learner.get(self.detail).json()['progress']['passed_ids'])
        self.assertEqual(self.answer(question, selected_ids=['a', 'b']).status_code, 409)

    def test_rejects_fake_media_and_removed_sources(self):
        bad = SimpleUploadedFile('bad.mp4', b'<html>no video</html>', content_type='video/mp4')
        self.assertEqual(self.teacher.post(self.url, {'title': 'Bad', 'duration': 30, 'file': bad}).status_code, 400)
        self.upload()
        self.assertEqual(self.teacher.delete(self.detail).status_code, 204)
        self.assertEqual(self.teacher.get(self.detail).status_code, 404)

    def test_wrong_without_rewind_keeps_the_checkpoint_and_counts_one_person(self):
        self.upload()
        question = self.question(start_time=0, rewind_time=None)
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        self.learner.get(self.detail)
        self.assertIsNone(self.answer(question, selected_ids=['a']).json()['rewind_to'])
        self.assertIsNone(self.answer(question, selected_ids=['b']).json()['rewind_to'])
        self.assertEqual(self.advance(1).status_code, 400)
        report = self.teacher.get(self.detail + 'responses/').json()
        self.assertEqual(report['questions'][0]['answered_students'], 1)
        self.assertEqual(report['questions'][0]['attempt_count'], 2)
        self.assertEqual(report['questions'][0]['correct_students'], 0)

    def test_question_bounds_and_revoked_enrollment(self):
        self.upload()
        base = {'kind': 'MCQ', 'prompt': 'Q', 'choices': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}], 'correct_ids': ['a'], 'start_time': 61}
        self.assertEqual(self.teacher.post(self.detail + 'questions/', base, format='json').status_code, 400)
        self.assertEqual(self.teacher.post(self.detail + 'questions/', {**base, 'start_time': 10, 'rewind_time': 10}, format='json').status_code, 400)
        self.question()
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        enrollment = self.room.enrollments.get(student=self.student.student_profile)
        enrollment.status = 'WITHDRAWN'
        enrollment.save()
        self.assertEqual(self.learner.get(self.detail).status_code, 404)
        self.assertEqual(self.learner.put(self.detail + 'progress/', {'position': 0}, format='json').status_code, 404)

    def test_duplicate_request_with_changed_payload_cannot_change_a_recorded_answer(self):
        self.upload()
        question = self.question(start_time=0, rewind_time=None)
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        self.learner.get(self.detail)
        import uuid
        payload = {'revision': 1, 'request_id': str(uuid.uuid4()), 'selected_ids': ['a']}
        url = self.detail + f'questions/{question["id"]}/answers/'
        self.assertEqual(self.learner.post(url, payload, format='json').status_code, 200)
        self.assertEqual(self.learner.post(url, {**payload, 'selected_ids': ['a', 'b']}, format='json').status_code, 400)

    def test_video_session_and_question_ids_cannot_be_mixed(self):
        self.upload()
        question = self.question()
        other = ClassroomSession.objects.create(classroom=self.room, is_draft=False)
        wrong = self.detail.replace(str(self.session.pk), str(other.pk))
        self.assertEqual(self.teacher.get(wrong).status_code, 404)
        self.assertEqual(self.teacher.patch(wrong + f'questions/{question["id"]}/', {'prompt': 'No'}, format='json').status_code, 404)
        self.session.removed_at = timezone.now()
        self.session.save()
        self.assertEqual(self.teacher.get(self.detail + 'file/').status_code, 404)

    def test_rapid_progress_requests_do_not_grant_new_playback_time(self):
        from unittest.mock import patch
        self.upload()
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        self.learner.get(self.detail)
        with patch('apps.courses.video_services.timezone.now', return_value=timezone.now()):
            self.assertEqual(self.learner.put(self.detail + 'progress/', {'position': 1}, format='json').status_code, 200)
            self.assertEqual(self.learner.put(self.detail + 'progress/', {'position': 2}, format='json').status_code, 400)
        self.assertEqual(self.advance(6).status_code, 200)

    def test_rewind_keeps_watched_frontier_and_resume_allows_seeking_inside_it(self):
        self.upload()
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        self.learner.get(self.detail)
        self.assertEqual(self.advance(5).status_code, 200)
        self.assertEqual(self.learner.put(self.detail + 'progress/', {'position': 1}, format='json').status_code, 200)
        restored = self.learner.get(self.detail).json()['progress']
        self.assertEqual(restored['position'], 1)
        self.assertEqual(restored['watched_until'], 5)
        self.assertEqual(restored['seekable_until'], 5)
        self.assertEqual(self.learner.put(self.detail + 'progress/', {'position': 3}, format='json').status_code, 200)
        self.assertEqual(self.learner.put(self.detail + 'progress/', {'position': 40}, format='json').status_code, 400)

    def test_completed_video_remains_watched_after_rewind_and_unlocks_all_seeking(self):
        self.upload()
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        self.learner.get(self.detail)
        for position in range(5, 61, 5):
            self.assertEqual(self.advance(position).status_code, 200)
        self.assertTrue(self.learner.get(self.detail).json()['progress']['completed'])
        self.learner.put(self.detail + 'progress/', {'position': 0}, format='json')
        self.assertTrue(self.learner.get(self.detail).json()['progress']['completed'])
        self.assertEqual(self.learner.put(self.detail + 'progress/', {'position': 50}, format='json').status_code, 200)

    def test_own_answer_history_is_private_and_survives_question_removal(self):
        self.upload()
        question = self.question(start_time=0, rewind_time=None)
        self.teacher.patch(self.detail, {'is_published': True}, format='json')
        self.learner.get(self.detail)
        self.answer(question, selected_ids=['a'])
        self.answer(question, selected_ids=['a', 'b'])
        self.teacher.delete(self.detail + f'questions/{question["id"]}/')
        response = self.learner.get(self.detail + 'answers/mine/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 2)
        self.assertEqual(response.json()['results'][0]['snapshot']['prompt'], 'Chọn đúng')
        self.assertNotIn('correct_ids', response.json()['results'][0]['snapshot'])
        outsider = authenticate_client(APIClient(), self.other)
        self.assertEqual(outsider.get(self.detail + 'answers/mine/').status_code, 404)
