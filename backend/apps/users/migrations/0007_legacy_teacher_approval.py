from django.db import migrations
from django.utils import timezone


def grant_legacy(apps, schema_editor):
    using = schema_editor.connection.alias
    User = apps.get_model('users', 'User')
    Profile = apps.get_model('users', 'TeacherProfile')
    Approval = apps.get_model('users', 'TeacherApproval')
    Event = apps.get_model('users', 'TeacherApprovalEvent')
    now = timezone.now()
    reason = 'Existing teacher at approval rollout; account and email verification unchanged.'
    for user in User.objects.using(using).select_for_update().filter(role='TEACHER').order_by('pk'):
        profile, _ = Profile.objects.using(using).get_or_create(user_id=user.pk)
        approval, created = Approval.objects.using(using).get_or_create(teacher_profile_id=profile.pk,
            defaults=dict(status='APPROVED', source='LEGACY', reason=reason,
                          approved_at=now, decided_at=now, revision=1))
        if not created:
            continue
        Event.objects.using(using).create(approval_id=approval.pk, action='LEGACY_APPROVED',
            reason=reason, revision=1, before={}, after=dict(
                status='APPROVED', source='LEGACY', reason=reason, revision=1,
                teacher_profile_id=str(profile.pk),
                institution_id=str(profile.institution_id) if profile.institution_id else None,
                institution_other_name=profile.institution_other_name,
                email_version_at_approval=None, approved_at=now.isoformat(), approved_by=None,
                decided_at=now.isoformat(), decided_by=None))


class Migration(migrations.Migration):
    dependencies = [('users', '0006_teacher_approval')]
    operations = [migrations.RunPython(grant_legacy, migrations.RunPython.noop)]
