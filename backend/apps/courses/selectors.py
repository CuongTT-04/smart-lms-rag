from apps.users.models import User

from .models import Course, CourseMember


def get_course(*, course_id):
    return Course.objects.filter(pk=course_id).first()


def list_course_members(*, course):
    return (
        CourseMember.objects.filter(course=course)
        .select_related("user")
        .order_by("joined_at", "id")
    )


def list_accessible_courses(*, user):
    if not user.is_authenticated or not user.is_active:
        return Course.objects.none()
    courses = Course.objects.filter(
        memberships__user=user,
        memberships__status=CourseMember.Status.ACTIVE,
        memberships__role__in=(
            [CourseMember.Role.OWNER]
            if user.role == User.Role.TEACHER
            else [CourseMember.Role.STUDENT]
        ),
    )
    if user.role == User.Role.TEACHER:
        return courses
    if user.role == User.Role.STUDENT:
        return courses.filter(status=Course.Status.PUBLISHED)
    return Course.objects.none()
