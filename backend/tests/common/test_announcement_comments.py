from django.test import TestCase
from rest_framework.test import APIClient
from apps.users.models import User
from apps.courses.models import Classroom, ClassroomAnnouncement, CourseMember, Enrollment
from apps.courses.services import create_course, update_course
from common.testing import authenticate_client


class AnnouncementCommentTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('comment-owner', role='TEACHER')
        self.student = User.objects.create_user('comment-student', role='STUDENT', full_name='Học viên A')
        self.peer = User.objects.create_user('comment-peer', role='STUDENT')
        self.outsider = User.objects.create_user('comment-outsider', role='STUDENT')
        self.course = create_course(actor=self.owner, title='Course')
        update_course(actor=self.owner, course=self.course, changes={'status': 'PUBLISHED'})
        self.room = Classroom.objects.create(course=self.course, name='Room')
        for user in [self.student, self.peer]:
            CourseMember.objects.create(course=self.course, user=user, role='STUDENT')
            Enrollment.objects.create(classroom=self.room, student=user.student_profile)
        self.post = ClassroomAnnouncement.objects.create(classroom=self.room, author=self.owner, content='Tin mới')
        self.base = f'/api/courses/{self.course.pk}/classrooms/{self.room.pk}/'
        self.url = self.base + f'announcements/{self.post.pk}/comments/'

    def client_for(self, user):
        return authenticate_client(APIClient(), user)

    def comment(self, user=None, **values):
        response = self.client_for(user or self.student).post(self.url, {'content': 'Bình luận', **values}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_comments_replies_and_vote_switching_are_shared_and_persisted(self):
        root = self.comment()
        self.comment(self.peer, content='Trả lời', parent_id=root['id'])
        client = self.client_for(self.peer)
        vote_url = self.url + root['id'] + '/vote/'
        for value, up, down in [(1, 1, 0), (-1, 0, 1), (-1, 0, 1), (0, 0, 0)]:
            response = client.put(vote_url, {'value': value}, format='json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual((response.json()['upvotes'], response.json()['downvotes']), (up, down))
        rows = self.client_for(self.owner).get(self.url).json()['results']
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['parent_id'], root['id'])
        self.assertEqual(rows[0]['author_name'], 'Học viên A')

    def test_students_delete_only_their_own_comments_and_teacher_can_moderate(self):
        root = self.comment()
        reply = self.comment(self.peer, parent_id=root['id'])
        self.assertEqual(self.client_for(self.peer).delete(self.url + root['id'] + '/').status_code, 403)
        self.assertEqual(self.client_for(self.student).delete(self.url + root['id'] + '/').status_code, 204)
        rows = self.client_for(self.peer).get(self.url).json()['results']
        self.assertTrue(rows[0]['is_deleted'])
        self.assertEqual(rows[0]['content'], '')
        self.assertEqual(rows[1]['content'], 'Bình luận')
        self.assertEqual(self.client_for(self.owner).delete(self.url + reply['id'] + '/').status_code, 204)

    def test_mute_blocks_posts_and_replies_across_announcements_until_unmuted(self):
        root = self.comment(self.owner)
        mute_url = self.base + f'comment-mutes/{self.student.pk}/'
        owner = self.client_for(self.owner)
        self.assertEqual(owner.put(mute_url, {'is_muted': True}, format='json').status_code, 200)
        client = self.client_for(self.student)
        self.assertFalse(client.get(self.url).json()['can_comment'])
        for values in [{'content': 'No'}, {'content': 'No reply', 'parent_id': root['id']}]:
            self.assertEqual(client.post(self.url, values, format='json').status_code, 403)
        another = ClassroomAnnouncement.objects.create(classroom=self.room, author=self.owner, content='Khác')
        other_url = self.base + f'announcements/{another.pk}/comments/'
        self.assertEqual(client.post(other_url, {'content': 'No'}, format='json').status_code, 403)
        self.assertEqual(owner.get(self.url).json()['muted_students'][0]['id'], str(self.student.pk))
        owner.put(mute_url, {'is_muted': False}, format='json')
        self.assertEqual(client.post(self.url, {'content': 'Được rồi'}, format='json').status_code, 201)

    def test_membership_and_parent_scope_are_enforced(self):
        client = self.client_for(self.outsider)
        self.assertEqual(client.get(self.url).status_code, 404)
        self.assertEqual(client.post(self.url, {'content': 'No'}, format='json').status_code, 404)
        root = self.comment()
        another = ClassroomAnnouncement.objects.create(classroom=self.room, author=self.owner, content='Khác')
        other_url = self.base + f'announcements/{another.pk}/comments/'
        client = self.client_for(self.student)
        self.assertEqual(client.post(other_url, {'content': 'Wrong parent', 'parent_id': root['id']}, format='json').status_code, 400)
        self.assertEqual(client.put(self.base + f'comment-mutes/{self.peer.pk}/', {'is_muted': True}, format='json').status_code, 404)
        member = CourseMember.objects.get(course=self.course, user=self.student)
        member.status = 'REMOVED'
        member.save()
        self.assertEqual(client.get(self.url).status_code, 404)
        self.assertEqual(client.put(self.url + root['id'] + '/vote/', {'value': 1}, format='json').status_code, 404)

    def test_blank_comments_and_invalid_votes_are_rejected(self):
        client = self.client_for(self.student)
        self.assertEqual(client.post(self.url, {'content': '  '}, format='json').status_code, 400)
        root = self.comment()
        self.assertEqual(client.put(self.url + root['id'] + '/vote/', {'value': 2}, format='json').status_code, 400)

    def test_vote_totals_survive_reload_without_exposing_other_users_votes(self):
        root = self.comment()
        vote_url = self.url + root['id'] + '/vote/'
        self.client_for(self.student).put(vote_url, {'value': 1}, format='json')
        self.client_for(self.peer).put(vote_url, {'value': -1}, format='json')
        row = self.client_for(self.owner).get(self.url).json()['results'][0]
        self.assertEqual((row['upvotes'], row['downvotes'], row['my_vote']), (1, 1, 0))
        row = self.client_for(self.student).get(self.url).json()['results'][0]
        self.assertEqual(row['my_vote'], 1)

    def test_mute_does_not_affect_another_class_and_removed_class_is_inaccessible(self):
        self.client_for(self.owner).put(self.base + f'comment-mutes/{self.student.pk}/', {'is_muted': True}, format='json')
        room = Classroom.objects.create(course=self.course, name='Other room')
        Enrollment.objects.create(classroom=room, student=self.student.student_profile)
        post = ClassroomAnnouncement.objects.create(classroom=room, author=self.owner, content='Other')
        url = f'/api/courses/{self.course.pk}/classrooms/{room.pk}/announcements/{post.pk}/comments/'
        client = self.client_for(self.student)
        self.assertEqual(client.post(url, {'content': 'Được bình luận lớp khác'}, format='json').status_code, 201)
        root = self.comment(self.owner)
        wrong_room_url = url + root['id'] + '/'
        self.assertEqual(self.client_for(self.owner).delete(wrong_room_url).status_code, 404)
        from django.utils import timezone
        self.room.removed_at = timezone.now()
        self.room.save()
        self.assertEqual(self.client_for(self.owner).get(self.url).status_code, 404)

