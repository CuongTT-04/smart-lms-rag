"""Permission integration must come from A; unavailable hooks fail closed."""
from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldError
from django.utils.module_loading import import_string
from .exceptions import DocumentError

def course_model():
    try:
        return apps.get_model(getattr(settings,"DOCUMENTS_COURSE_MODEL","courses.Course"))
    except (LookupError,ValueError) as exc:
        raise DocumentError("COURSE_INTEGRATION_MISSING","A must supply the Course model.",503) from exc

def refresh_live_user(user):
    if not getattr(user, "is_authenticated", False):
        raise DocumentError("AUTH_REQUIRED", "Authentication required.", 401)
    if getattr(user, "pk", None) is not None and hasattr(user, "refresh_from_db"):
        try:
            user.refresh_from_db(fields=["is_active", "status", "role"])
        except user.__class__.DoesNotExist as exc:
            raise DocumentError("AUTH_REQUIRED", "Authentication required.", 401) from exc
        except (FieldError, TypeError):
            try:
                user.refresh_from_db()
            except user.__class__.DoesNotExist as exc:
                raise DocumentError("AUTH_REQUIRED", "Authentication required.", 401) from exc
    if not user.is_active or getattr(user, "status", "ACTIVE") != "ACTIVE":
        raise DocumentError("AUTH_REQUIRED", "Authentication required.", 401)
    return user


def require_access(user,course,manage=False):
    refresh_live_user(user)
    from apps.users.teaching_access import require_teacher_approval
    require_teacher_approval(user)
    name="DOCUMENTS_MANAGE_PERMISSION" if manage else "DOCUMENTS_READ_PERMISSION"
    default="apps.courses.permissions.can_manage_course" if manage else "apps.courses.permissions.can_view_course"
    try: provider=import_string(getattr(settings,name,default))
    except (ImportError,AttributeError) as exc:
        raise DocumentError("PERMISSION_INTEGRATION_MISSING","A must supply course permission selectors.",503) from exc
    if not callable(provider):raise DocumentError("PERMISSION_INTEGRATION_MISSING","Invalid permission provider.",503)
    if not provider(user,course):raise DocumentError("NOT_FOUND","Resource unavailable.",404)


def require_session_access(user, session, course, manage=False):
    from apps.courses.permissions import can_manage_course, can_view_classroom
    require_access(user, course, manage=manage)
    if session.removed_at or session.classroom.removed_at or session.classroom.course_id != course.pk or (not manage and not can_view_classroom(user, session.classroom)):
        raise DocumentError('NOT_FOUND', 'Resource unavailable.', 404)
    if session.is_draft and not can_manage_course(user, course):
        raise DocumentError('NOT_FOUND', 'Resource unavailable.', 404)
