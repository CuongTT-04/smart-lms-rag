from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from apps.users.models import TeacherApproval, User
from common.testing import authenticate_client

PASSWORD = 'Account-Test-839!'


class AccountApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser('account_admin', password=PASSWORD)
        self.target = User.objects.create_user('target', email='target@example.com', password=PASSWORD)
        self.client = authenticate_client(APIClient(), self.admin)

    def url(self, suffix=''):
        return f'/api/operations/users/{self.target.pk}/{suffix}'

    def body(self, **values):
        self.target.refresh_from_db()
        return dict(reason='Đã đối chiếu hồ sơ.', current_password=PASSWORD,
                    expected_updated_at=self.target.updated_at.isoformat(), **values)

    def test_list_is_paginated_filtered_and_never_exposes_credentials(self):
        response = self.client.get('/api/operations/users/?role=STUDENT&q=target&limit=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['username'], 'target')
        self.assertNotIn('password', response.data['results'][0])
        self.assertNotIn('user_permissions', response.data['results'][0])
        self.assertEqual(self.client.get('/api/operations/users/?limit=101').status_code, 400)

    def test_lists_keep_verified_teachers_when_verification_filter_is_omitted(self):
        from django.utils import timezone
        from apps.users.teacher_approval import auto_approve_verified_teacher
        teacher = User.objects.create_user('verified_teacher', role='TEACHER',
            email='teacher@ptit.edu.vn', email_verified_at=timezone.now())
        auto_approve_verified_teacher(teacher)
        self.assertEqual(TeacherApproval.objects.get(teacher_profile__user=teacher).status, 'APPROVED')
        for url in ('/api/operations/users/', '/api/operations/teachers/',
                    '/api/operations/teachers/?approval_status=APPROVED'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('verified_teacher', [row['username'] for row in response.data['results']])
        verified = self.client.get('/api/operations/users/?email_verified=true')
        self.assertEqual([row['username'] for row in verified.data['results']], ['verified_teacher'])
        unverified = self.client.get('/api/operations/users/?email_verified=false')
        self.assertNotIn('verified_teacher', [row['username'] for row in unverified.data['results']])

    def test_non_admin_and_admin_without_permission_cannot_read(self):
        for role in ('STUDENT', 'TEACHER', 'ADMIN'):
            user = User.objects.create_user('denied_' + role, role=role)
            client = authenticate_client(APIClient(), user)
            self.assertEqual(client.get('/api/operations/users/').status_code, 403)

    def test_read_only_admin_cannot_write(self):
        viewer = User.objects.create_user('viewer', role='ADMIN', password=PASSWORD)
        viewer.user_permissions.add(Permission.objects.get(codename='view_user'))
        client = authenticate_client(APIClient(), viewer)
        self.assertEqual(client.get('/api/operations/users/').status_code, 200)
        self.assertEqual(client.patch(self.url(), self.body(status='BLOCKED'), format='json').status_code, 403)

    def test_block_revokes_old_access_even_after_unlock_and_audits(self):
        old_client = authenticate_client(APIClient(), self.target)
        response = self.client.patch(self.url(), self.body(status='BLOCKED'), format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(old_client.get('/api/users/me/').status_code, 401)
        self.assertEqual(self.client.patch(self.url(), self.body(status='ACTIVE'), format='json').status_code, 200)
        self.assertEqual(old_client.get('/api/users/me/').status_code, 401)
        history = self.client.get(self.url('history/'))
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data['count'], 2)
        self.assertNotIn(PASSWORD, str(history.data))

    def test_sensitive_writes_require_password_reason_and_current_revision(self):
        for changes in ({'current_password': 'wrong'}, {'reason': ''}, {'expected_updated_at': '2020-01-01T00:00:00Z'}):
            body = self.body(status='BLOCKED')
            body.update(changes)
            response = self.client.patch(self.url(), body, format='json')
            self.assertIn(response.status_code, (400, 403, 409))
        self.target.refresh_from_db()
        self.assertEqual(self.target.status, 'ACTIVE')
        self.assertFalse(LogEntry.objects.filter(object_id=str(self.target.pk)).exists())

    def test_unknown_fields_and_self_privilege_changes_are_rejected(self):
        for field in ('is_superuser', 'is_staff', 'auth_version', 'role', 'email_verified_at', 'groups'):
            self.assertEqual(self.client.patch(self.url(), self.body(**{field: True}), format='json').status_code, 400)
        self.target = self.admin
        self.assertEqual(self.client.patch(self.url(), self.body(status='BLOCKED'), format='json').status_code, 400)
        self.assertEqual(self.client.post(self.url('role/'), self.body(role='STUDENT'), format='json').status_code, 400)

    def test_create_teacher_stays_pending_and_does_not_verify_email(self):
        response = self.client.post('/api/operations/users/', dict(username='new_teacher', full_name='Giáo viên mới', email='new@ptit.edu.vn',
            password=PASSWORD, role='TEACHER', institution_other_name='Trường tự khai',
            reason='Tạo hồ sơ theo đề nghị.', current_password=PASSWORD), format='json')
        self.assertEqual(response.status_code, 201)
        teacher = User.objects.get(username='new_teacher')
        self.assertIsNone(teacher.email_verified_at)
        self.assertEqual(teacher.teacher_profile.approval.status, 'PENDING')
        self.assertEqual(response.data['teacher_profile']['approval']['revision'], teacher.teacher_profile.approval.revision)
        self.assertNotIn(PASSWORD, str(list(LogEntry.objects.values_list('change_message', flat=True))))

    def test_role_change_preserves_profiles_and_requires_separate_permission(self):
        old_profile = self.target.student_profile.pk
        response = self.client.post(self.url('role/'), self.body(role='TEACHER'), format='json')
        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.student_profile.pk, old_profile)
        self.assertEqual(self.target.teacher_profile.approval.status, 'PENDING')
        operator = User.objects.create_user('operator', role='ADMIN', password=PASSWORD)
        operator.user_permissions.add(Permission.objects.get(codename='change_user'))
        client = authenticate_client(APIClient(), operator)
        self.assertEqual(client.post(self.url('role/'), self.body(role='ADMIN'), format='json').status_code, 403)

    def test_approval_decision_and_history_use_revision(self):
        teacher = User.objects.create_user('review_teacher', role='TEACHER')
        url = f'/api/operations/teachers/{teacher.pk}/approval/'
        body = dict(status='APPROVED', reason='Đủ điều kiện giảng dạy.', expected_revision=1, current_password=PASSWORD)
        response = self.client.post(url, body, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'APPROVED')
        self.assertEqual(self.client.post(url, body, format='json').status_code, 409)
        history = self.client.get(url + 'history/')
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data['count'], 2)
        listing = self.client.get('/api/operations/teachers/?approval_status=APPROVED')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['count'], 1)

    def test_delete_is_not_available(self):
        self.assertEqual(self.client.delete(self.url()).status_code, 405)

    def test_last_effective_admin_is_protected_from_change_only_operator(self):
        User.objects.create_superuser('unusable_admin', password=None)
        operator = User.objects.create_user('limited_operator', role='ADMIN', password=PASSWORD)
        operator.user_permissions.add(Permission.objects.get(codename='change_user'))
        client = authenticate_client(APIClient(), operator)
        self.target = self.admin
        response = client.patch(self.url(), self.body(status='BLOCKED'), format='json')
        self.assertEqual(response.status_code, 409)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.status, 'ACTIVE')

    def test_owning_teacher_cannot_change_role_until_courses_are_archived(self):
        from apps.courses.models import Course, CourseMember
        self.target = User.objects.create_user('owning_teacher', role='TEACHER')
        course = Course.objects.create(title='Khóa đang quản lý')
        member = CourseMember.objects.create(course=course, user=self.target, role='OWNER')
        self.assertEqual(self.client.post(self.url('role/'), self.body(role='STUDENT'), format='json').status_code, 409)
        course.status = 'ARCHIVED'
        course.save()
        self.assertEqual(self.client.post(self.url('role/'), self.body(role='STUDENT'), format='json').status_code, 200)
        self.assertTrue(CourseMember.objects.filter(pk=member.pk).exists())
        self.assertEqual(self.client.post(self.url('role/'), self.body(role='TEACHER'), format='json').status_code, 200)
        self.assertEqual(TeacherApproval.objects.get(teacher_profile__user=self.target).status, 'PENDING')

    def test_audit_failure_rolls_back_status_and_session_version(self):
        previous_version = self.target.auth_version
        with patch('apps.users.account_administration.audit_account', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.patch(self.url(), self.body(status='BLOCKED'), format='json')
        self.target.refresh_from_db()
        self.assertEqual((self.target.status, self.target.auth_version), ('ACTIVE', previous_version))

    def test_email_edit_invalidates_verification_and_does_not_log_email_values(self):
        from django.utils import timezone
        self.target.email_verified_at = timezone.now()
        self.target.save(update_fields=['email_verified_at'])
        self.assertEqual(self.client.patch(self.url(), self.body(email='changed@example.com'), format='json').status_code, 200)
        self.target.refresh_from_db()
        self.assertFalse(self.target.email_verified)
        audit = self.client.get(self.url('history/')).data
        self.assertNotIn('changed@example.com', str(audit))
        self.assertNotIn('target@example.com', str(audit))

    def test_change_only_admin_cannot_replace_superuser_recovery_email(self):
        operator = User.objects.create_user('recovery_operator', role='ADMIN', password=PASSWORD)
        operator.user_permissions.add(Permission.objects.get(codename='change_user'))
        client = authenticate_client(APIClient(), operator)
        self.target = self.admin
        original_email = self.admin.email
        response = client.patch(self.url(), self.body(email='attacker@example.com'), format='json')
        self.assertEqual(response.status_code, 403)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.email, original_email)
        self.assertFalse(LogEntry.objects.filter(object_id=str(self.admin.pk)).exists())

    def test_cannot_edit_admin_with_stronger_group_or_staff_permissions(self):
        from django.contrib.auth.models import Group
        operator = User.objects.create_user('lower_admin', role='ADMIN', password=PASSWORD)
        operator.user_permissions.add(Permission.objects.get(codename='change_user'))
        client = authenticate_client(APIClient(), operator)
        group = Group.objects.create(name='Privileged target')
        group.permissions.add(Permission.objects.get(codename='assign_user_role'))
        for staff in (False, True):
            with self.subTest(staff=staff):
                self.target = User.objects.create_user('higher_admin_' + str(staff), role='ADMIN',
                    is_staff=staff, email=f'higher-{staff}@example.com', password=PASSWORD)
                if not staff:
                    self.target.groups.add(group)
                original_email = self.target.email
                response = client.patch(self.url(), self.body(email=f'changed-{staff}@example.com'), format='json')
                self.assertEqual(response.status_code, 403)
                self.target.refresh_from_db()
                self.assertEqual(self.target.email, original_email)

    def test_demoting_superuser_revokes_django_privileges_and_existing_sessions(self):
        from django.contrib.auth.models import Group
        from django.test import Client
        group = Group.objects.create(name='Former admin group')
        group.permissions.add(Permission.objects.get(codename='assign_user_role'))
        for role in ('STUDENT', 'TEACHER'):
            with self.subTest(role=role):
                self.target = User.objects.create_superuser('demoted_' + role, password=PASSWORD)
                self.target.groups.add(group)
                self.target.user_permissions.add(Permission.objects.get(codename='change_user'))
                jwt_client = authenticate_client(APIClient(), self.target)
                django_client = Client()
                django_client.force_login(self.target)
                self.assertEqual(django_client.get('/admin/').status_code, 200)
                response = self.client.post(self.url('role/'), self.body(role=role), format='json')
                self.assertEqual(response.status_code, 200)
                self.target.refresh_from_db()
                self.assertEqual(self.target.role, role)
                self.assertFalse(self.target.is_staff)
                self.assertFalse(self.target.is_superuser)
                self.assertFalse(self.target.groups.exists())
                self.assertFalse(self.target.user_permissions.exists())
                self.assertEqual(jwt_client.get('/api/users/me/').status_code, 401)
                self.assertEqual(django_client.get('/admin/').status_code, 302)
                self.assertFalse(self.target.has_perm('users.change_user'))
                self.assertEqual(self.client.post(self.url('role/'), self.body(role='ADMIN'), format='json').status_code, 200)
                self.target.refresh_from_db()
                self.assertFalse(self.target.is_staff or self.target.is_superuser)
                self.assertFalse(self.target.groups.exists() or self.target.user_permissions.exists())

    def test_blocked_privileged_admin_cannot_be_taken_over_or_reactivated_by_lower_admin(self):
        operator = User.objects.create_user('blocked_operator', role='ADMIN', password=PASSWORD)
        operator.user_permissions.add(Permission.objects.get(codename='change_user'))
        self.target = User.objects.create_user('blocked_privileged', role='ADMIN', status='BLOCKED',
            email='blocked@example.com', password=PASSWORD)
        self.target.user_permissions.add(Permission.objects.get(codename='assign_user_role'))
        client = authenticate_client(APIClient(), operator)
        for values in ({'email': 'takeover@example.com'}, {'status': 'ACTIVE'}):
            self.assertEqual(client.patch(self.url(), self.body(**values), format='json').status_code, 403)
        self.target.refresh_from_db()
        self.assertEqual((self.target.email, self.target.status), ('blocked@example.com', 'BLOCKED'))

    def test_failed_demotion_audit_rolls_back_privilege_revocation(self):
        self.target = User.objects.create_superuser('rollback_superuser', password=PASSWORD)
        permission = Permission.objects.get(codename='change_user')
        self.target.user_permissions.add(permission)
        with patch('apps.users.account_administration.audit_account', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url('role/'), self.body(role='STUDENT'), format='json')
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, 'ADMIN')
        self.assertTrue(self.target.is_staff and self.target.is_superuser)
        self.assertTrue(self.target.user_permissions.filter(pk=permission.pk).exists())

    def test_permission_removed_is_effective_with_old_jwt(self):
        viewer = User.objects.create_user('removed_viewer', role='ADMIN')
        permission = Permission.objects.get(codename='view_user')
        viewer.user_permissions.add(permission)
        client = authenticate_client(APIClient(), viewer)
        self.assertEqual(client.get('/api/operations/users/').status_code, 200)
        viewer.user_permissions.remove(permission)
        self.assertEqual(client.get('/api/operations/users/').status_code, 403)

    def test_bootstrap_is_repeatable_and_does_not_promote_students(self):
        from django.contrib.auth.models import Group
        from io import StringIO
        call_command('seed_admin_groups', stdout=StringIO())
        call_command('seed_admin_groups', stdout=StringIO())
        self.assertEqual(Group.objects.filter(name__startswith='OHAYO ').count(), 4)
        with self.assertRaises(CommandError):
            call_command('seed_admin_groups', assign=self.target.username, group='OHAYO Role Manager', reason='Không được nâng vai trò.', stdout=StringIO())
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, 'STUDENT')
        self.assertFalse(self.target.groups.exists())

    def test_bootstrap_assignment_requires_authorized_actor_and_logs_that_actor(self):
        from io import StringIO
        user = User.objects.create_user('new_admin', role='ADMIN')
        call_command('seed_admin_groups', assign=user.username, group='OHAYO Account Manager',
                     actor=self.admin.username, reason='Cấp nhiệm vụ quản trị.', stdout=StringIO())
        user.refresh_from_db()
        self.assertTrue(user.has_perm('users.change_user'))
        self.assertFalse(user.has_perm('users.assign_user_role'))
        entry = LogEntry.objects.get(object_id=str(user.pk))
        self.assertEqual(entry.user_id, self.admin.pk)
        with self.assertRaises(CommandError):
            call_command('seed_admin_groups', assign=user.username, group='OHAYO Role Manager',
                         actor=user.username, reason='Không được tự nâng quyền.', stdout=StringIO())


class LastAdminConcurrencyTests(TransactionTestCase):
    def test_two_updates_with_same_timestamp_only_apply_once(self):
        admin = User.objects.create_superuser('parallel_admin', password=PASSWORD)
        target = User.objects.create_user('parallel_target')
        barrier = Barrier(2)

        def update(status):
            close_old_connections()
            try:
                client = authenticate_client(APIClient(), admin)
                barrier.wait(timeout=10)
                return client.patch(f'/api/operations/users/{target.pk}/', dict(status=status,
                    reason='Cập nhật cùng phiên bản.', current_password=PASSWORD,
                    expected_updated_at=target.updated_at.isoformat()), format='json').status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(update, ('BLOCKED', 'INACTIVE')))
        self.assertCountEqual(results, [200, 409])
        self.assertEqual(LogEntry.objects.filter(object_id=str(target.pk)).count(), 1)

    def test_two_admins_cannot_remove_each_other_simultaneously(self):
        admins = [User.objects.create_superuser('last_' + str(i), password=PASSWORD) for i in range(2)]
        barrier = Barrier(2)

        def block(index):
            close_old_connections()
            try:
                actor, target = admins[index], admins[1-index]
                client = authenticate_client(APIClient(), actor)
                barrier.wait(timeout=10)
                return client.patch(f'/api/operations/users/{target.pk}/', dict(status='BLOCKED',
                    reason='Kiểm xử lý đồng thời.', current_password=PASSWORD,
                    expected_updated_at=target.updated_at.isoformat()), format='json').status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(block, range(2)))
        self.assertEqual(results.count(200), 1, results)
        self.assertTrue(all(code in (200, 401, 403, 409) for code in results), results)
        self.assertEqual(User.objects.filter(role='ADMIN', status='ACTIVE', is_active=True).count(), 1)
