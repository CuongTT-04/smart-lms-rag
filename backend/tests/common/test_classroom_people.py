from django.test import TestCase
from rest_framework.test import APIClient
from apps.users.models import User
from apps.courses.models import Classroom, CourseMember, Enrollment
from apps.courses.services import create_course, update_course
from common.testing import authenticate_client


class ClassroomPeopleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('people-owner', role='TEACHER', full_name='Teacher')
        self.student = User.objects.create_user('people-student', role='STUDENT', full_name='Student')
        self.other = User.objects.create_user('people-other', role='STUDENT')
        self.course = create_course(actor=self.owner, title='Course')
        update_course(actor=self.owner, course=self.course, changes={'status':'PUBLISHED'})
        self.room = Classroom.objects.create(course=self.course, name='Room')
        CourseMember.objects.create(course=self.course, user=self.student, role='STUDENT', status='ACTIVE')
        self.enrollment = Enrollment.objects.create(classroom=self.room, student=self.student.student_profile)
        self.url = f'/api/courses/{self.course.pk}/classrooms/{self.room.pk}/people/'

    def test_student_can_read_names_separated_from_owner_without_contact_or_progress(self):
        client = authenticate_client(APIClient(), self.student)
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'owners':[{'id':str(self.owner.pk),'name':'Teacher'}], 'students':[{'id':str(self.student.pk),'name':'Student'}]})
        self.assertEqual(client.post(self.url, {}, format='json').status_code, 405)

    def test_other_students_and_withdrawn_enrollment_cannot_read(self):
        self.assertEqual(authenticate_client(APIClient(), self.other).get(self.url).status_code, 404)
        self.enrollment.status = 'WITHDRAWN'
        self.enrollment.save()
        self.assertEqual(authenticate_client(APIClient(), self.student).get(self.url).status_code, 404)
        response = authenticate_client(APIClient(), self.owner).get(self.url)
        self.assertEqual(response.json()['students'], [])

    def test_list_contains_classmates_but_excludes_other_classes_and_revoked_members(self):
        member = CourseMember.objects.create(course=self.course, user=self.other, role='STUDENT', status='ACTIVE')
        enrollment = Enrollment.objects.create(classroom=self.room, student=self.other.student_profile)
        client = authenticate_client(APIClient(), self.student)
        ids = lambda: {person['id'] for person in client.get(self.url).json()['students']}
        self.assertEqual(ids(), {str(self.student.pk), str(self.other.pk)})
        other_room = Classroom.objects.create(course=self.course, name='Other room')
        enrollment.classroom = other_room
        enrollment.save()
        self.assertEqual(ids(), {str(self.student.pk)})
        enrollment.classroom = self.room
        enrollment.save()
        member.status = 'REMOVED'
        member.save()
        self.assertEqual(ids(), {str(self.student.pk)})
