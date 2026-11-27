from datetime import datetime, timezone as dt_timezone
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.assessment_models import Assessment, AssessmentAttempt
from apps.courses.models import Classroom, ClassroomSession, Course
from apps.users.models import User
from common.testing import authenticate_client


class OverviewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('overview_admin', password='Overview-Test-839!')
        self.client = authenticate_client(APIClient(), self.admin)

    def test_submission_period_uses_local_midnight_and_excludes_drafts(self):
        course = Course.objects.create(title='Khóa kiểm tổng quan')
        classroom = Classroom.objects.create(course=course, name='Lớp kiểm')
        session = ClassroomSession.objects.create(classroom=classroom, title='Buổi kiểm')
        assessment = Assessment.objects.create(session=session, title='Bài kiểm', kind='TEXT', mode='PRACTICE', due_at=timezone.now())
        # 27 November local spans [26 November 17:00Z, 27 November 17:00Z).
        for number, submitted in enumerate([
                datetime(2026, 11, 26, 16, 59, 59, tzinfo=dt_timezone.utc),
                datetime(2026, 11, 26, 17, 0, tzinfo=dt_timezone.utc),
                datetime(2026, 11, 27, 16, 59, 59, tzinfo=dt_timezone.utc),
                datetime(2026, 11, 27, 17, 0, tzinfo=dt_timezone.utc), None], 1):
            AssessmentAttempt.objects.create(assessment=assessment, student=self.admin, request_id=uuid4(),
                number=number, status='SUBMITTED' if submitted else 'DRAFT', submitted_at=submitted, expires_at=timezone.now())
        response = self.client.get('/api/operations/overview/?start_date=2026-11-27&end_date=2026-11-27')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['submitted_attempts'], 2)
        self.assertEqual(response.data['timezone'], 'Asia/Ho_Chi_Minh')
        self.assertEqual((response.data['courses'], response.data['classrooms']), (1, 1))
        self.assertEqual(response.data['accounts']['total'], 1)
        self.assertIn('definitions', response.data)

    def test_overview_requires_distinct_permission_and_date_validation(self):
        user = User.objects.create_user('overview_denied', role='ADMIN')
        client = authenticate_client(APIClient(), user)
        self.assertEqual(client.get('/api/operations/overview/').status_code, 403)
        for query in ('start_date=2026-11-28&end_date=2026-11-27', 'end_date=invalid',
                      'end_date=0001-01-01', 'start_date=2020-01-01&end_date=2026-11-27'):
            self.assertEqual(self.client.get('/api/operations/overview/?' + query).status_code, 400)
