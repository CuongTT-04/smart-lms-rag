"""Live teaching eligibility; never authorize from cached profile/approval objects."""
from django.core.exceptions import PermissionDenied

from .models import User
from .teacher_approval import is_education_email


class TeacherNotApproved(PermissionDenied):
    code = 'TEACHER_NOT_APPROVED'
    message = 'Tài khoản chưa đủ điều kiện giảng dạy. Vui lòng kiểm tra trạng thái xét duyệt.'

    def __init__(self):
        super().__init__({'code': self.code, 'message': self.message})


def teaching_state(user):
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'pk', None):
        return None
    return User.objects.filter(pk=user.pk).values('role', 'status', 'is_active', 'email', 'email_version',
        'email_verified_at', 'teacher_profile__approval__status', 'teacher_profile__approval__source',
        'teacher_profile__approval__email_version_at_approval').first()


def allowed(state):
    if not state or state['role'] != 'TEACHER' or not state['is_active'] or state['status'] != 'ACTIVE':
        return False
    if state['teacher_profile__approval__status'] != 'APPROVED':
        return False
    if state['teacher_profile__approval__source'] == 'AUTO_EDU_VN':
        return bool(state['email_verified_at'] and is_education_email(state['email']) and
                    state['email_version'] == state['teacher_profile__approval__email_version_at_approval'])
    return state['teacher_profile__approval__source'] in ('ADMIN', 'LEGACY')


def has_teaching_approval(user):
    return allowed(teaching_state(user))


def require_teacher_approval(user):
    state = teaching_state(user)
    if state and state['role'] == 'TEACHER' and not allowed(state):
        raise TeacherNotApproved()


def guard_teaching_request(request, user):
    if user.role != 'TEACHER':
        return
    path = request.path_info.rstrip('/')
    if path == '/api/courses' and request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    match = getattr(request, 'resolver_match', None)
    namespaces = set(getattr(match, 'app_names', []) or [])
    teaching_apps = {'courses', 'course-documents', 'documents', 'assessments', 'learning', 'ai'}
    if namespaces & teaching_apps or path.startswith(('/api/courses/', '/api/documents/', '/api/assessments/', '/api/learning/', '/api/ai/')):
        require_teacher_approval(user)
