from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from apps.courses.models import Classroom
from apps.courses.services import create_course, update_course
from apps.users.models import User
from common.testing import authenticate_client

class ClassroomPolicyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user('policy-owner', role='TEACHER')
        self.student = User.objects.create_user('policy-student')
        self.course = create_course(actor=self.owner, title='Policy test')
        update_course(actor=self.owner, course=self.course, changes={'status': 'PUBLISHED'})
        self.first = self.course.classrooms.get()
        self.second = Classroom.objects.create(course=self.course, name='Second')
        self.client = authenticate_client(APIClient(), self.owner)

    def test_atomic_edit_is_isolated_and_join_uses_classroom_approval(self):
        url = f'/api/courses/{self.course.pk}/classrooms/{self.first.pk}/'
        response = self.client.patch(url, {'name': 'Changed', 'visibility': 'PUBLIC', 'require_approval': True, 'is_join_enabled': True}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.first.refresh_from_db(); self.second.refresh_from_db()
        self.assertTrue(self.first.require_approval)
        self.assertFalse(self.second.require_approval)
        self.assertEqual(self.second.visibility, 'PRIVATE')
        student = authenticate_client(APIClient(), self.student)
        pending = student.post(reverse('courses:join'), {'class_code': self.first.class_code}, format='json')
        self.assertEqual(pending.json()['status'], 'PENDING')
        joined = student.post(reverse('courses:join'), {'class_code': self.second.class_code}, format='json')
        self.assertEqual(joined.json()['status'], 'ENROLLED')

    def test_invalid_settings_do_not_partially_rename_and_student_cannot_edit(self):
        url = f'/api/courses/{self.course.pk}/classrooms/{self.first.pk}/'
        original = self.first.name
        self.assertEqual(self.client.patch(url, {'name': 'Invalid rename', 'visibility': 'INVALID'}, format='json').status_code, 400)
        self.first.refresh_from_db(); self.assertEqual(self.first.name, original)
        student = authenticate_client(APIClient(), self.student)
        self.assertEqual(student.patch(url, {'require_approval': False}, format='json').status_code, 403)
