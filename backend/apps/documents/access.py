"""Permission integration must come from A; unavailable hooks fail closed."""
from django.apps import apps
from django.conf import settings
from django.utils.module_loading import import_string
from .exceptions import DocumentError

def course_model():
    try:
        return apps.get_model(getattr(settings,"DOCUMENTS_COURSE_MODEL","courses.Course"))
    except (LookupError,ValueError) as exc:
        raise DocumentError("COURSE_INTEGRATION_MISSING","A must supply the Course model.",503) from exc

def require_access(user,course,manage=False):
    if not user.is_authenticated or not user.is_active:
        raise DocumentError("AUTH_REQUIRED","Authentication required.",401)
    name="DOCUMENTS_MANAGE_PERMISSION" if manage else "DOCUMENTS_READ_PERMISSION"
    default="apps.courses.permissions.can_manage_course" if manage else "apps.courses.permissions.can_view_course"
    try: provider=import_string(getattr(settings,name,default))
    except (ImportError,AttributeError) as exc:
        raise DocumentError("PERMISSION_INTEGRATION_MISSING","A must supply course permission selectors.",503) from exc
    if not callable(provider):raise DocumentError("PERMISSION_INTEGRATION_MISSING","Invalid permission provider.",503)
    if not provider(user,course):raise DocumentError("NOT_FOUND","Resource unavailable.",404)


def require_session_access(user, session, course, manage=False):
    from apps.courses.permissions import can_view_classroom
    require_access(user, course, manage=manage)
    if session.removed_at or session.classroom.course_id != course.pk or (not manage and not can_view_classroom(user, session.classroom)):
        raise DocumentError('NOT_FOUND', 'Resource unavailable.', 404)
