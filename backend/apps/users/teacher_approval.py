"""Teacher decisions serialized on the User row shared with email confirmation."""
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from .models import TeacherApproval, TeacherApprovalEvent, TeacherProfile, User


class ApprovalConflict(ValidationError):
    def __init__(self):
        super().__init__('Teacher approval changed; reload before deciding.', code='APPROVAL_REVISION_CONFLICT')


def is_education_email(email):
    if not isinstance(email, str) or email.strip().count('@') != 1:
        return False
    email = email.strip()
    try:
        validate_email(email)
        domain = email.rsplit('@', 1)[1].encode('idna').decode('ascii').lower()
    except (ValidationError, UnicodeError):
        return False
    return domain.endswith('.edu.vn') and not domain.endswith('.')


def snapshot(approval, profile):
    return dict(status=approval.status, source=approval.source, reason=approval.reason, revision=approval.revision,
        teacher_profile_id=str(profile.pk), institution_id=str(profile.institution_id) if profile.institution_id else None,
        institution_other_name=profile.institution_other_name,
        email_version=profile.user.email_version,
        email_version_at_approval=approval.email_version_at_approval,
        approved_at=approval.approved_at.isoformat() if approval.approved_at else None,
        approved_by=str(approval.approved_by_id) if approval.approved_by_id else None,
        decided_at=approval.decided_at.isoformat() if approval.decided_at else None,
        decided_by=str(approval.decided_by_id) if approval.decided_by_id else None)


def record(approval, profile, before, action, reason, actor=None, *, using='default'):
    TeacherApprovalEvent.objects.db_manager(using).create(approval=approval, actor=actor,
        action=action, reason=reason, revision=approval.revision, before=before, after=snapshot(approval, profile))


def ensure_teacher_approval(profile, *, using='default'):
    with transaction.atomic(using=using):
        user = User.objects.using(using).select_for_update().get(pk=profile.user_id)
        if user.role != User.Role.TEACHER:
            return None
        approval, created = TeacherApproval.objects.using(using).get_or_create(teacher_profile=profile)
        if created:
            record(approval, profile, {}, 'CREATED', 'New teacher awaiting review.', using=using)
        return approval


@transaction.atomic
def auto_approve_verified_teacher(user):
    current = User.objects.select_for_update().get(pk=user.pk)
    if current.role != User.Role.TEACHER or not current.is_active or current.status != User.Status.ACTIVE:
        return
    if not current.email_verified or not is_education_email(current.email):
        return
    profile = TeacherProfile.objects.filter(user=current).first()
    if profile is None:
        return
    ensure_teacher_approval(profile)
    approval = TeacherApproval.objects.select_for_update().get(teacher_profile=profile)
    if approval.status != TeacherApproval.Status.PENDING:
        return
    before = snapshot(approval, profile)
    approval.status = TeacherApproval.Status.APPROVED
    approval.source = TeacherApproval.Source.AUTO_EDU_VN
    approval.reason = 'Verified email domain ends with .edu.vn.'
    approval.revision += 1
    approval.approved_at = approval.decided_at = timezone.now()
    approval.email_version_at_approval = current.email_version
    approval.save()
    record(approval, profile, before, 'AUTO_APPROVED', approval.reason)


@transaction.atomic
def decide_teacher_approval(*, actor, teacher_profile_id, status, reason, expected_revision):
    if status not in ('APPROVED', 'REJECTED', 'REVOKED'):
        raise ValidationError({'status': 'Choose APPROVED, REJECTED or REVOKED.'})
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ValidationError({'reason': 'Provide a reason of at most 1000 characters.'})
    if type(expected_revision) is not int or expected_revision < 1:
        raise ValidationError({'revision': 'Provide a positive integer revision.'})
    profile = TeacherProfile.objects.get(pk=teacher_profile_id)
    # Stable ordering also covers two administrators deciding about each other.
    users = {user.pk: user for user in User.objects.select_for_update().filter(
        pk__in={actor.pk, profile.user_id}).order_by('pk')}
    admin = users.get(actor.pk)
    if admin is None or admin.role != User.Role.ADMIN or not admin.is_active or admin.status != User.Status.ACTIVE or not admin.has_perm('users.change_teacherapproval'):
        raise PermissionError('Teacher approval administration permission required.')
    teacher = users.get(profile.user_id)
    if teacher is None or teacher.role != User.Role.TEACHER:
        raise ValidationError({'teacher': 'This profile does not belong to a teacher.'})
    profile = TeacherProfile.objects.get(pk=teacher_profile_id, user_id=teacher.pk)
    ensure_teacher_approval(profile)
    approval = TeacherApproval.objects.select_for_update().get(teacher_profile=profile)
    if approval.revision != expected_revision:
        raise ApprovalConflict()
    if approval.status == status:
        return approval
    allowed = {'PENDING': {'APPROVED', 'REJECTED'}, 'APPROVED': {'REVOKED'},
               'REJECTED': {'APPROVED'}, 'REVOKED': {'APPROVED'}}
    if status not in allowed[approval.status]:
        raise ValidationError({'status': 'Invalid approval transition; reload and choose a supported action.'})
    before = snapshot(approval, profile)
    approval.status = status
    approval.source = TeacherApproval.Source.ADMIN
    approval.reason = reason.strip()
    approval.revision += 1
    approval.decided_at = timezone.now()
    approval.decided_by = admin
    if status == TeacherApproval.Status.APPROVED:
        approval.approved_at = approval.decided_at
        approval.approved_by = admin
        approval.email_version_at_approval = teacher.email_version
    approval.save()
    record(approval, profile, before, 'ADMIN_' + status, approval.reason, admin)
    return approval


def teacher_email_changed(user, *, previous_email_version, using='default'):
    with transaction.atomic(using=using):
        current = User.objects.using(using).select_for_update().get(pk=user.pk)
        profile = TeacherProfile.objects.using(using).filter(user=current).first()
        if profile is None:
            return
        approval = TeacherApproval.objects.using(using).select_for_update().filter(teacher_profile=profile).first()
        if approval is None:
            return
        before = snapshot(approval, profile)
        before['email_version'] = previous_email_version
        if approval.status == 'APPROVED' and approval.source == 'AUTO_EDU_VN':
            approval.status, approval.source = 'PENDING', ''
            approval.reason = 'Email changed; verification and review required.'
            approval.approved_at = approval.decided_at = None
            approval.approved_by = approval.decided_by = None
            approval.email_version_at_approval = None
        approval.revision += 1
        approval.save(using=using)
        record(approval, profile, before, 'EMAIL_CHANGED', 'Email version changed; verification cleared.', current, using=using)


def teacher_affiliation_changed(profile, previous, *, actor=None, using='default'):
    current = TeacherProfile.objects.using(using).get(pk=profile.pk)
    if current.institution_id == previous['institution_id'] and current.institution_other_name == previous['institution_other_name']:
        return
    approval = TeacherApproval.objects.using(using).select_for_update().filter(teacher_profile=current).first()
    if approval is None:
        return
    before = snapshot(approval, current)
    before.update(institution_id=str(previous['institution_id']) if previous['institution_id'] else None,
                  institution_other_name=previous['institution_other_name'])
    approval.revision += 1
    approval.save(using=using)
    record(approval, current, before, 'AFFILIATION_CHANGED', 'Self-declared school affiliation changed.', actor, using=using)
