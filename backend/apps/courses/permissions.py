from rest_framework.permissions import BasePermission

from apps.users.models import User

from .models import Course, CourseMember


def can_create_course(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and user.role == User.Role.TEACHER
    )


def can_manage_course(user, course):
    return can_create_course(user) and CourseMember.objects.filter(
        course=course,
        user=user,
        role=CourseMember.Role.OWNER,
        status=CourseMember.Status.ACTIVE,
    ).exists()


def can_view_course(user, course):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.role == User.Role.TEACHER:
        return can_manage_course(user, course)
    return (
        user.role == User.Role.STUDENT
        and course.status == Course.Status.PUBLISHED
        and CourseMember.objects.filter(
            course=course,
            user=user,
            role=CourseMember.Role.STUDENT,
            status=CourseMember.Status.ACTIVE,
        ).exists()
    )


class IsTeacher(BasePermission):
    message = "Only active teachers can create courses."

    def has_permission(self, request, view):
        return can_create_course(request.user)


class CanManageCourse(BasePermission):
    message = "Only the active course owner can manage this course."

    def has_permission(self, request, view):
        return can_create_course(request.user)

    def has_object_permission(self, request, view, obj):
        return can_manage_course(request.user, obj)


class CanViewCourse(BasePermission):
    message = "You do not have access to this course."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_active

    def has_object_permission(self, request, view, obj):
        return can_view_course(request.user, obj)


def can_view_classroom(user, classroom):
    if can_manage_course(user, classroom.course):
        return True
    return can_view_course(user, classroom.course) and classroom.enrollments.filter(
        student__user=user, status__in=['ACTIVE', 'COMPLETED'],
    ).exists()
