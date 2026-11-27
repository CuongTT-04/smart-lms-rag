"""Account writes: live permissions, step-up password, serialization and safe audit."""
import json

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from .models import StudentProfile, TeacherApproval, TeacherProfile, User
from .teacher_approval import record, snapshot


class AccountConflict(ValidationError):
    pass


def require_account_admin(actor, *permissions):
    current = User.objects.filter(pk=actor.pk, role='ADMIN', status='ACTIVE', is_active=True).first()
    if current is None or current.auth_version != actor.auth_version or not all(
            current.has_perm(permission if '.' in permission else 'users.' + permission) for permission in permissions):
        raise PermissionError('Bạn không có quyền quản trị này hoặc phiên đã thay đổi.')
    return current


def lock_administration():
    # All account mutation paths share one transaction lock, including last-admin checks.
    # Production and integration tests use PostgreSQL, as required by this application.
    if connection.vendor != 'postgresql':
        raise RuntimeError('Account administration requires PostgreSQL transaction locks.')
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [487239105])


def authorize_write(actor, password, reason, *permissions, user_id=None):
    lock_administration()
    ids = {actor.pk, user_id} if user_id else {actor.pk}
    locked = {user.pk: user for user in User.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
    current = locked[actor.pk]
    current = require_account_admin(current, *permissions)
    if current.auth_version != actor.auth_version:
        raise PermissionError('Phiên đã thay đổi. Vui lòng đăng nhập lại.')
    if not isinstance(password, str) or not current.check_password(password):
        raise PermissionError('Xác nhận lại mật khẩu quản trị để tiếp tục.')
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ValidationError({'reason': 'Cần lý do từ 1 đến 1000 ký tự.'})
    return current


def account_snapshot(user):
    # No passwords, tokens, email addresses, phone or arbitrary client fields in audit.
    return dict(role=user.role, status=user.status, auth_version=user.auth_version,
                email_version=user.email_version, updated_at=user.updated_at.isoformat())


def audit_account(actor, user, action, reason, before, changed_fields):
    LogEntry.objects.create(user=actor, content_type=ContentType.objects.get_for_model(User),
        object_id=str(user.pk), object_repr=str(user.pk), action_flag=ADDITION if action == 'CREATED' else CHANGE,
        change_message=json.dumps(dict(action=action, result='APPLIED', reason=reason.strip(), before=before,
            after=account_snapshot(user), changed_fields=sorted(changed_fields)), ensure_ascii=False))


def effective_admin(user):
    return bool(user.role == 'ADMIN' and user.status == 'ACTIVE' and user.is_active and user.has_usable_password() and
        (user.is_superuser or (user.has_perm('users.change_user') and user.has_perm('users.assign_user_role'))))


def protect_last_admin(target, *, role=None, status=None):
    if not effective_admin(target):
        return
    if (role is not None and role != 'ADMIN') or (status is not None and status != 'ACTIVE'):
        others = User.objects.filter(role='ADMIN', status='ACTIVE', is_active=True).exclude(pk=target.pk)
        if not any(effective_admin(user) for user in others):
            raise AccountConflict('Không thể vô hiệu hóa quản trị viên hữu hiệu cuối cùng.')


def reset_teacher_decision(user, actor, reason, *, entering):
    profile, _ = TeacherProfile.objects.get_or_create(user=user)
    approval = TeacherApproval.objects.select_for_update().get(teacher_profile=profile)
    before = snapshot(approval, profile)
    approval.status = 'PENDING' if entering else 'REVOKED'
    approval.source = '' if entering else 'ADMIN'
    approval.reason = reason.strip()
    approval.revision += 1
    approval.decided_by = None if entering else actor
    approval.decided_at = None if entering else timezone.now()
    if entering:
        approval.approved_by = approval.approved_at = approval.email_version_at_approval = None
    approval.save()
    record(approval, profile, before, 'ROLE_ENTERED' if entering else 'ROLE_REMOVED', reason.strip(), actor)


@transaction.atomic
def create_administered_user(*, actor, values, current_password, reason):
    admin = authorize_write(actor, current_password, reason, 'add_user')
    from .api.serializers import RegistrationSerializer
    if not isinstance(values, dict) or set(values) - {
            'username', 'email', 'full_name', 'phone', 'password', 'role', 'institution_id', 'institution_other_name'}:
        raise ValidationError({'detail': 'Trường tạo tài khoản không được hỗ trợ.'})
    raw = dict(values)
    raw['password_confirm'] = raw.get('password')
    serializer = RegistrationSerializer(data=raw)
    serializer.is_valid(raise_exception=True)
    fields = dict(serializer.validated_data)
    institution_id = fields.pop('institution_id')
    school = fields.pop('institution_other_name')
    for name in ('bio', 'specialization', 'learning_goal'):
        fields.pop(name)
    password = fields.pop('password')
    user = User.objects.create_user(password=password, **fields)
    if user.role == 'TEACHER':
        profile = user.teacher_profile
        profile.institution_id, profile.institution_other_name = institution_id, school
        profile.save(update_fields=['institution', 'institution_other_name', 'updated_at'])
    audit_account(admin, user, 'CREATED', reason, {}, set(values) - {'password'})
    user.refresh_from_db()
    return user


@transaction.atomic
def update_administered_user(*, actor, user_id, values, current_password, reason, expected_updated_at, role_change=False):
    permissions = ('change_user', 'assign_user_role') if role_change else ('change_user',)
    admin = authorize_write(actor, current_password, reason, *permissions, user_id=user_id)
    target = User.objects.select_for_update().get(pk=user_id)
    if target.updated_at != expected_updated_at:
        raise AccountConflict('Tài khoản đã thay đổi. Tải lại trước khi cập nhật.')
    allowed_fields = {'role'} if role_change else {'full_name', 'email', 'phone', 'status'}
    if not values or set(values) - allowed_fields:
        raise ValidationError({'detail': 'Chỉ được sửa các trường quản trị cho phép.'})
    if target.pk == admin.pk and set(values) & {'role', 'status'}:
        raise ValidationError({'detail': 'Không tự đổi vai trò hoặc trạng thái của mình.'})
    if 'role' in values and values['role'] not in User.Role.values:
        raise ValidationError({'role': 'Vai trò không hợp lệ.'})
    if 'status' in values and values['status'] not in User.Status.values:
        raise ValidationError({'status': 'Trạng thái không hợp lệ.'})
    protect_last_admin(target, role=values.get('role'), status=values.get('status'))
    old_role = target.role
    if role_change and old_role == 'TEACHER' and values['role'] != old_role:
        from apps.courses.models import CourseMember
        if CourseMember.objects.filter(user=target, role='OWNER', status='ACTIVE').exclude(course__status='ARCHIVED').exists():
            raise AccountConflict('Cần xử lý quyền sở hữu khóa học chưa lưu trữ trước khi đổi vai trò.')
    before = account_snapshot(target)
    changed = {key for key, value in values.items() if getattr(target, key) != value}
    if not changed:
        return target
    for key, value in values.items():
        setattr(target, key, value)
    target.is_active = target.status == 'ACTIVE'
    target.full_clean(exclude=['password'])
    target.save(update_fields=changed)
    if old_role != target.role:
        if old_role == 'TEACHER':
            reset_teacher_decision(target, admin, reason, entering=False)
        if target.role == 'STUDENT':
            StudentProfile.objects.get_or_create(user=target)
        if target.role == 'TEACHER':
            reset_teacher_decision(target, admin, reason, entering=True)
    if target.auth_version != before['auth_version']:
        from .services import _schedule_close_user_sockets, revoke_refresh_tokens
        revoke_refresh_tokens(target)
        _schedule_close_user_sockets(target.pk)
    audit_account(admin, target, 'ROLE_CHANGED' if role_change else 'UPDATED', reason, before, changed)
    target.refresh_from_db()
    return target


@transaction.atomic
def administer_teacher_decision(*, actor, user_id, status, reason, current_password, expected_revision):
    admin = authorize_write(actor, current_password, reason, 'change_teacherapproval', user_id=user_id)
    target = User.objects.select_for_update().get(pk=user_id)
    if target.role != 'TEACHER':
        raise ValidationError({'teacher': 'Đối tượng hiện không phải giáo viên.'})
    from .teacher_approval import decide_teacher_approval
    return decide_teacher_approval(actor=admin, teacher_profile_id=target.teacher_profile.pk,
        status=status, reason=reason, expected_revision=expected_revision)
