from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.email_verification import confirm_email_verification, hash_verification_token, on_email_verified
from apps.users.models import EmailVerificationToken, TeacherApproval, TeacherApprovalEvent, User
from apps.users.teacher_approval import ApprovalConflict, decide_teacher_approval, is_education_email
from common.testing import authenticate_client


class TeacherApprovalTests(TestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user('pending_teacher', email='teacher@ptit.edu.vn', role='TEACHER')
        self.admin = User.objects.create_superuser('approval_admin', password='Approval-Test-839!')

    def approval(self):
        return TeacherApproval.objects.get(teacher_profile__user=self.teacher)

    def decide(self, status, **kwargs):
        obj = self.approval()
        return decide_teacher_approval(actor=self.admin, teacher_profile_id=obj.teacher_profile_id,
            status=status, reason='Reviewed by administrator.', expected_revision=obj.revision, **kwargs)

    def verify(self):
        token = 'teacher-confirmation-token-' + str(EmailVerificationToken.objects.filter(user=self.teacher).count())
        EmailVerificationToken.objects.create(user=self.teacher, email=self.teacher.email,
            email_version=self.teacher.email_version, token_hash=hash_verification_token(token),
            expires_at=timezone.now() + timezone.timedelta(hours=1))
        return confirm_email_verification(token=token)

    def test_new_teacher_pending_and_student_has_no_approval(self):
        approval = self.approval()
        self.assertEqual(approval.status, 'PENDING')
        self.assertEqual(approval.source, '')
        self.assertEqual(approval.revision, 1)
        self.assertIsNone(approval.approved_at)
        self.assertEqual(approval.events.count(), 1)
        student = User.objects.create_user('student', email='student@ptit.edu.vn')
        self.assertFalse(TeacherApproval.objects.filter(teacher_profile__user=student).exists())

    def test_pending_audit_failure_rolls_back_new_teacher_and_profile(self):
        with patch.object(TeacherApprovalEvent.objects, 'create', side_effect=RuntimeError('Audit failure')):
            with self.assertRaises(RuntimeError):
                User.objects.create_user('atomic_teacher', role='TEACHER')
        self.assertFalse(User.objects.filter(username='atomic_teacher').exists())

    def test_startup_hook_registration_is_not_duplicated(self):
        from django.apps import apps
        from apps.users.email_verification import _email_verified_hooks
        from apps.users.teacher_approval import auto_approve_verified_teacher
        apps.get_app_config('users').ready()
        apps.get_app_config('users').ready()
        self.assertEqual(_email_verified_hooks.count(auto_approve_verified_teacher), 1)

    def test_domain_matching_not_website_or_substring(self):
        for email in [' Teacher@PTIT.EDU.VN ', 'teacher@stu.ptit.edu.vn']:
            self.assertTrue(is_education_email(email), email)
        for email in ['x@fakeedu.vn', 'x@ptit.edu.vn.attacker.com', 'edu.vn@evil.com', 'x@edu.vn',
                      'x@@ptit.edu.vn', 'x@.edu.vn', 'not-an-email', None, 'x@ptit.edu.vn.']:
            self.assertFalse(is_education_email(email), email)

    def test_auto_approval_is_in_confirmation_transaction_and_idempotent(self):
        self.assertEqual(self.approval().status, 'PENDING')
        self.verify()
        approval = self.approval()
        self.assertEqual((approval.status, approval.source), ('APPROVED', 'AUTO_EDU_VN'))
        self.assertEqual(approval.email_version_at_approval, 1)
        self.assertIsNotNone(approval.approved_at)
        self.assertIsNone(approval.approved_by_id)
        self.assertEqual(approval.revision, 2)
        self.assertEqual(approval.events.count(), 2)
        on_email_verified(self.teacher)
        self.assertEqual(self.approval().events.count(), 2)

    def test_confirmation_uses_user_first_lock_order(self):
        locked_queries = []
        def capture(execute, sql, params, many, context):
            if 'FOR UPDATE' in sql:
                locked_queries.append(sql)
            return execute(sql, params, many, context)
        with connection.execute_wrapper(capture):
            self.verify()
        self.assertIn('"users_user"', locked_queries[0])
        self.assertIn('"users_emailverificationtoken"', locked_queries[1])

    def test_unverified_wrong_role_or_non_school_email_not_auto_approved(self):
        on_email_verified(self.teacher)
        self.assertEqual(self.approval().status, 'PENDING')
        self.teacher.email = 'teacher@fakeedu.vn'; self.teacher.save(update_fields=['email'])
        self.verify()
        self.assertEqual(self.approval().status, 'PENDING')
        student = User.objects.create_user('school_student', email='s@ptit.edu.vn', email_verified_at=timezone.now())
        on_email_verified(student)
        self.assertFalse(TeacherApproval.objects.filter(teacher_profile__user=student).exists())

    def test_rejected_or_revoked_not_restored_by_verification(self):
        self.decide('REJECTED')
        self.verify()
        self.assertEqual(self.approval().status, 'REJECTED')
        self.decide('APPROVED'); self.decide('REVOKED')
        on_email_verified(self.teacher)
        self.assertEqual(self.approval().status, 'REVOKED')
        self.assertEqual(self.approval().source, 'ADMIN')

    def test_admin_reapproval_requires_explicit_decision_and_keeps_audit(self):
        self.decide('REJECTED')
        approval = self.decide('APPROVED')
        self.assertEqual(approval.approved_by_id, self.admin.pk)
        self.assertEqual(approval.source, 'ADMIN')
        self.decide('REVOKED')
        approval = self.decide('APPROVED')
        self.assertEqual(approval.revision, 5)
        self.assertEqual(list(approval.events.order_by('revision').values_list('revision', flat=True)), [1, 2, 3, 4, 5])
        event = approval.events.latest('revision')
        self.assertEqual(event.before['status'], 'REVOKED')
        self.assertEqual(event.after['status'], 'APPROVED')
        self.assertEqual(event.actor_id, self.admin.pk)

    def test_reason_revision_permissions_and_transition_validation(self):
        obj = self.approval()
        args = dict(actor=self.admin, teacher_profile_id=obj.teacher_profile_id, status='APPROVED', reason='Reviewed.', expected_revision=1)
        for change in [{'reason': ' '}, {'reason': 'x' * 1001}, {'expected_revision': True}, {'status': 'PENDING'}]:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                decide_teacher_approval(**{**args, **change})
        with self.assertRaises(ValidationError):
            self.decide('REVOKED')
        limited = User.objects.create_user('limited_admin', role='ADMIN')
        with self.assertRaises(PermissionError):
            decide_teacher_approval(**{**args, 'actor': limited})
        limited.user_permissions.add(Permission.objects.get(codename='change_teacherapproval'))
        decide_teacher_approval(**{**args, 'actor': limited})
        with self.assertRaises(ApprovalConflict):
            decide_teacher_approval(**args)

    def test_stale_admin_role_and_same_status_do_not_write(self):
        first = self.decide('APPROVED')
        count = first.events.count()
        self.decide('APPROVED')
        self.assertEqual(first.events.count(), count)
        User.objects.filter(pk=self.admin.pk).update(role='STUDENT')
        with self.assertRaises(PermissionError):
            self.decide('REVOKED')

    def test_email_change_removes_auto_approval_but_not_admin_rejection(self):
        self.verify()
        self.teacher.refresh_from_db()
        self.teacher.email = 'changed@example.com'; self.teacher.save(update_fields=['email'])
        approval = self.approval()
        self.assertEqual((approval.status, approval.source), ('PENDING', ''))
        self.assertIsNone(approval.email_version_at_approval)
        self.assertFalse(self.teacher.email_verified)
        self.assertEqual(approval.events.latest('revision').action, 'EMAIL_CHANGED')
        event = approval.events.latest('revision')
        self.assertEqual((event.before['email_version'], event.after['email_version']), (1, 2))
        self.decide('REJECTED')
        self.teacher.email = 'again@ptit.edu.vn'; self.teacher.save(update_fields=['email'])
        self.assertEqual(self.approval().status, 'REJECTED')
        self.verify()
        self.assertEqual(self.approval().status, 'REJECTED')

    def test_admin_approval_survives_email_change_without_faking_verification(self):
        self.decide('APPROVED')
        self.teacher.email = 'new@example.com'; self.teacher.save(update_fields=['email'])
        self.assertEqual((self.approval().status, self.approval().source), ('APPROVED', 'ADMIN'))
        self.assertFalse(self.teacher.email_verified)

    def test_blocked_account_is_not_unlocked_or_auto_approved(self):
        self.teacher.email_verified_at = timezone.now()
        self.teacher.status = 'BLOCKED'; self.teacher.save()
        on_email_verified(self.teacher)
        self.assertEqual(self.approval().status, 'PENDING')
        self.decide('APPROVED')
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.is_active)
        self.assertEqual(self.teacher.status, 'BLOCKED')

    def test_confirmation_rolls_back_email_and_token_if_approval_audit_fails(self):
        with patch.object(TeacherApprovalEvent.objects, 'create', side_effect=RuntimeError('Audit failure')):
            with self.assertRaises(RuntimeError):
                self.verify()
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.email_verified)
        self.assertIsNone(EmailVerificationToken.objects.get(user=self.teacher).used_at)
        self.assertEqual(self.approval().status, 'PENDING')

    def test_own_profile_exposes_read_only_status_and_tampering_is_rejected(self):
        client = authenticate_client(APIClient(), self.teacher)
        response = client.get('/api/users/me/')
        self.assertEqual(response.data['user']['teacher_profile']['approval']['status'], 'PENDING')
        response = client.patch('/api/users/me/', {'teacher_profile': {'approval': {'status': 'APPROVED'}}}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.approval().status, 'PENDING')

    def test_registration_creates_pending_and_affiliation_audit_atomically(self):
        data = dict(username='signup_teacher', email='signup@ptit.edu.vn', password='Approval-Test-839!',
                    password_confirm='Approval-Test-839!', full_name='Teacher', role='TEACHER', institution_other_name='Trường tự khai')
        response = APIClient().post('/api/users/register/', data, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['user']['teacher_profile']['approval']['status'], 'PENDING')
        user = User.objects.get(username='signup_teacher')
        event = user.teacher_profile.approval.events.latest('revision')
        self.assertEqual(event.action, 'AFFILIATION_CHANGED')
        self.assertEqual(event.after['institution_other_name'], 'Trường tự khai')
        self.assertEqual(event.actor_id, user.pk)
        for key in ['approval_status', 'approved_by', 'email_verified_at']:
            self.assertEqual(APIClient().post('/api/users/register/', {**data, key: 'APPROVED'}, format='json').status_code, 400)


class TeacherApprovalConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.teacher = User.objects.create_user('concurrent_teacher', role='TEACHER',
                                               email='teacher@ptit.edu.vn', email_verified_at=timezone.now())
        self.admin = User.objects.create_superuser('concurrent_admin', password='Approval-Test-839!')

    def test_verification_callback_cannot_undo_concurrent_revocation(self):
        approval = self.teacher.teacher_profile.approval
        decide_teacher_approval(actor=self.admin, teacher_profile_id=approval.teacher_profile_id,
                                status='APPROVED', reason='Initial approval.', expected_revision=1)
        barrier = Barrier(2)
        def run(auto):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if auto:
                    on_email_verified(self.teacher)
                else:
                    decide_teacher_approval(actor=self.admin, teacher_profile_id=approval.teacher_profile_id,
                                            status='REVOKED', reason='Revoked after review.', expected_revision=2)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(run, flag) for flag in [True, False]]
            for job in jobs:
                job.result(timeout=20)
        approval.refresh_from_db()
        self.assertEqual(approval.status, 'REVOKED')
        self.assertEqual(approval.revision, 3)

    def test_two_admin_decisions_use_optimistic_revision_without_lost_updates(self):
        profile = self.teacher.teacher_profile
        barrier = Barrier(2)
        def run(status):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    decide_teacher_approval(actor=self.admin, teacher_profile_id=profile.pk,
                                            status=status, reason='Concurrent review.', expected_revision=1)
                    return 'applied'
                except ApprovalConflict:
                    return 'conflict'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, ['APPROVED', 'REJECTED']))
        self.assertCountEqual(results, ['applied', 'conflict'])
        self.assertEqual(profile.approval.events.count(), 2)

    def test_email_change_and_confirmation_do_not_deadlock_or_leave_stale_approval(self):
        self.teacher.email_verified_at = None
        self.teacher.save(update_fields=['email_verified_at'])
        raw = 'concurrent-email-change-confirmation'
        EmailVerificationToken.objects.create(user=self.teacher, email=self.teacher.email,
            email_version=self.teacher.email_version, token_hash=hash_verification_token(raw),
            expires_at=timezone.now() + timezone.timedelta(hours=1))
        barrier = Barrier(2)
        def run(confirm):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if confirm:
                    try:
                        confirm_email_verification(token=raw)
                    except ValidationError:
                        pass
                else:
                    user = User.objects.get(pk=self.teacher.pk)
                    user.email = 'changed@example.com'
                    user.save(update_fields=['email'])
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(run, flag) for flag in [True, False]]
            for job in jobs:
                job.result(timeout=20)
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.email_verified)
        self.assertEqual(self.teacher.email_version, 2)
        self.assertEqual(self.teacher.teacher_profile.approval.status, 'PENDING')


class TeacherApprovalMigrationTests(TransactionTestCase):
    def test_legacy_is_idempotent_preserves_locked_users_and_excludes_new_pending(self):
        executor = MigrationExecutor(connection)
        before = [('users', '0005_institutions')]
        after = [('users', '0007_legacy_teacher_approval')]
        executor.migrate(before)
        try:
            old = executor.loader.project_state(before).apps
            OldUser = old.get_model('users', 'User')
            OldProfile = old.get_model('users', 'TeacherProfile')
            user = OldUser.objects.create(username='legacy_locked', email='old@example.com', role='TEACHER',
                                          status='BLOCKED', is_active=False, email_version=3, auth_version=4)
            profile = OldProfile.objects.create(user_id=user.pk)
            executor = MigrationExecutor(connection); executor.migrate(after)
            approval = TeacherApproval.objects.get(teacher_profile_id=profile.pk)
            self.assertEqual((approval.status, approval.source), ('APPROVED', 'LEGACY'))
            user = User.objects.get(pk=user.pk)
            self.assertEqual((user.status, user.is_active, user.email_verified_at, user.auth_version), ('BLOCKED', False, None, 4))
            self.assertIsNone(approval.email_version_at_approval)
            self.assertEqual(approval.events.count(), 1)
            newcomer = User.objects.create_user('after_migration', role='TEACHER')
            admin = User.objects.create_superuser('legacy_reviewer', password='Approval-Test-839!')
            decide_teacher_approval(actor=admin, teacher_profile_id=profile.pk,
                                    status='REVOKED', reason='Manual revocation.', expected_revision=1)
            module = import_module('apps.users.migrations.0007_legacy_teacher_approval')
            with connection.schema_editor() as schema_editor:
                module.grant_legacy(executor.loader.project_state(after).apps, schema_editor)
            self.assertEqual(TeacherApproval.objects.get(pk=approval.pk).status, 'REVOKED')
            self.assertEqual(newcomer.teacher_profile.approval.status, 'PENDING')
            self.assertEqual(TeacherApproval.objects.get(pk=approval.pk).events.count(), 2)
        finally:
            MigrationExecutor(connection).migrate(after)
