from django.db.models import Prefetch

from apps.users.models import User

from .models import Course, CourseMember, Enrollment


def with_student_classrooms(courses, user):
    if user and user.is_authenticated and user.role == User.Role.STUDENT:
        return courses.prefetch_related(Prefetch(
            "classrooms__enrollments",
            queryset=Enrollment.objects.filter(student__user=user).exclude(
                status=Enrollment.Status.WITHDRAWN
            ).select_related("classroom__course").order_by("enrolled_at", "id"),
            to_attr="student_enrollments",
        ))
    return courses


def get_course(*, course_id, user=None):
    return with_student_classrooms(Course.objects.filter(pk=course_id), user).first()


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
        return with_student_classrooms(courses.filter(status=Course.Status.PUBLISHED), user)
    return Course.objects.none()
