from django.core.signals import request_finished
from django.db import close_old_connections
from apps.users.authentication import issue_access_token


def authenticate_client(client, user):
    """Attach a short-lived bearer token to a DRF APIClient."""
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_access_token(user)}")
    return client


def approved_teacher(user):
    """Explicit existing-teacher fixture; never used by registration/production code."""
    from django.utils import timezone
    from apps.users.models import TeacherApproval
    from apps.users.teacher_approval import record, snapshot
    if user.role != 'TEACHER':
        return user
    profile = user.teacher_profile
    approval = TeacherApproval.objects.get(teacher_profile=profile)
    before = snapshot(approval, profile)
    approval.status, approval.source = 'APPROVED', 'LEGACY'
    approval.reason = 'Explicit approved teacher test fixture.'
    approval.approved_at = approval.decided_at = timezone.now()
    approval.revision += 1
    approval.save()
    record(approval, profile, before, 'FIXTURE_APPROVED', approval.reason)
    profile._state.fields_cache.pop('approval', None)
    return user


def close_response(response):
    """Close a streaming test response without letting request_finished drop TestCase atomics."""
    connected = request_finished.disconnect(close_old_connections)
    try:
        response.close()
    finally:
        if connected:
            request_finished.connect(close_old_connections)
