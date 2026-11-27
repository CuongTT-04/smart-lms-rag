from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Course, CourseMember
from apps.courses.permissions import can_create_course, can_manage_course
from apps.courses.services import create_course, update_course
from apps.users.models import User
from apps.users.teaching_access import has_teaching_approval
from apps.users.teacher_approval import decide_teacher_approval
from common.testing import authenticate_client, approved_teacher


class TeachingAccessTests(TestCase):
    def setUp(self):
        self.pending = User.objects.create_user('pending_access', role='TEACHER', email='pending@example.com')
        self.owner = approved_teacher(User.objects.create_user('approved_owner', role='TEACHER'))
        self.admin = User.objects.create_superuser('access_admin')
        self.course = create_course(actor=self.owner, title='Existing course')
        self.client = authenticate_client(APIClient(), self.pending)

    def test_pending_can_login_read_profile_and_empty_course_shell_but_not_create(self):
        self.assertEqual(self.client.get('/api/users/me/').status_code, 200)
        response = self.client.get('/api/courses/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [])
        response = self.client.post('/api/courses/', {'title': 'Blocked'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'TEACHER_NOT_APPROVED')
        self.assertFalse(Course.objects.filter(title='Blocked').exists())

    def test_all_teaching_api_families_deny_before_payload_and_resource_work(self):
        c, room, session, item = (str(uuid4()) for _ in range(4))
        paths = [
            (f'/api/courses/{c}/', 'patch'),
            (f'/api/courses/{c}/classrooms/', 'post'),
            (f'/api/courses/{c}/classrooms/{room}/sessions/', 'post'),
            (f'/api/courses/{c}/classrooms/{room}/announcements/', 'post'),
            (f'/api/courses/{c}/classrooms/{room}/sessions/{session}/videos/', 'post'),
            (f'/api/courses/{c}/classrooms/{room}/sessions/{session}/assessments/', 'post'),
            (f'/api/courses/{c}/access-policy/', 'patch'),
            (f'/api/courses/{c}/documents/', 'post'),
            (f'/api/documents/{item}/view/', 'get'),
            ('/api/ai/chat/', 'post'),
            ('/api/ai/conversations/', 'get'),
        ]
        with patch('apps.ai.api.views.answer_chat') as generate:
            for path, method in paths:
                with self.subTest(path=path):
                    response = getattr(self.client, method)(path, {} if method != 'get' else None, format='json')
                    self.assertEqual(response.status_code, 403, (path, response.data))
                    self.assertEqual(response.data.get('code') or response.data.get('error', {}).get('code'), 'TEACHER_NOT_APPROVED')
            generate.assert_not_called()

    def test_stale_actor_and_old_jwt_cannot_keep_teaching_after_revocation(self):
        client = authenticate_client(APIClient(), self.owner)
        self.assertTrue(has_teaching_approval(self.owner))
        approval = self.owner.teacher_profile.approval
        decide_teacher_approval(actor=self.admin, teacher_profile_id=self.owner.teacher_profile.pk,
            status='REVOKED', reason='Access revoked.', expected_revision=approval.revision)
        self.assertFalse(can_create_course(self.owner))
        self.assertFalse(can_manage_course(self.owner, self.course))
        with self.assertRaises(PermissionDenied):
            create_course(actor=self.owner, title='Stale create')
        with self.assertRaises(PermissionDenied):
            update_course(actor=self.owner, course=self.course, changes={'title': 'Stale update'})
        response = client.patch(f'/api/courses/{self.course.pk}/', {'title': 'Stale API'}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (403, 'TEACHER_NOT_APPROVED'))
        self.course.refresh_from_db(); self.assertEqual(self.course.title, 'Existing course')

    def test_auto_approval_requires_current_email_evidence_even_if_state_was_cached(self):
        self.pending.email = 'teacher@ptit.edu.vn'
        self.pending.save(update_fields=['email'])
        self.pending.email_verified_at = timezone.now()
        self.pending.save(update_fields=['email_verified_at'])
        from apps.users.email_verification import on_email_verified
        on_email_verified(self.pending)
        self.assertTrue(has_teaching_approval(self.pending))
        User.objects.filter(pk=self.pending.pk).update(email='changed@example.com')
        self.assertFalse(has_teaching_approval(self.pending))

    def test_approved_owner_still_scoped_to_own_course_and_student_not_escalated(self):
        self.assertTrue(can_manage_course(self.owner, self.course))
        self.assertFalse(can_manage_course(self.owner, Course.objects.create(title='Not owned')))
        student = User.objects.create_user('ordinary_student')
        self.assertFalse(has_teaching_approval(student))
        response = authenticate_client(APIClient(), student).post('/api/courses/', {'title': 'No'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('teacher_profile', authenticate_client(APIClient(), student).get('/api/users/me/').data['user'])

    def test_profile_has_authoritative_teaching_allowed_without_client_control(self):
        response = self.client.get('/api/users/me/')
        self.assertFalse(response.data['user']['teaching_allowed'])
        self.assertEqual(self.client.patch('/api/users/me/', {'teaching_allowed': True}, format='json').status_code, 400)
        response = authenticate_client(APIClient(), self.owner).get('/api/users/me/')
        self.assertTrue(response.data['user']['teaching_allowed'])
