from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Course, CourseMember
from .permissions import can_create_course, can_manage_course


@transaction.atomic
def create_course(*, actor, title, description=""):
    if not can_create_course(actor):
        raise PermissionDenied("Only active teachers can create courses.")

    course = Course(title=title, description=description)
    course.full_clean()
    course.save()
    member = CourseMember(
        course=course,
        user=actor,
        role=CourseMember.Role.OWNER,
        status=CourseMember.Status.ACTIVE,
    )
    member.full_clean()
    member.save()
    return course


@transaction.atomic
def update_course(*, actor, course, changes):
    course = Course.objects.select_for_update().get(pk=course.pk)
    if not can_manage_course(actor, course):
        raise PermissionDenied("You cannot manage this course.")
    unexpected = set(changes) - {"title", "description", "status"}
    if unexpected:
        raise ValidationError({field: "This field cannot be updated." for field in unexpected})
    if not changes:
        raise ValidationError("Provide at least one field to update.")

    for field, value in changes.items():
        setattr(course, field, value)
    if course.status == Course.Status.PUBLISHED and course.published_at is None:
        course.published_at = timezone.now()
    course.full_clean()
    course.save()
    return course


@transaction.atomic
def grant_student_access(*, actor, course, user_id):
    course = Course.objects.select_for_update().get(pk=course.pk)
    if not can_manage_course(actor, course):
        raise PermissionDenied("You cannot manage this course.")

    User = get_user_model()
    student = User.objects.select_for_update().filter(pk=user_id).first()
    if student is None or not student.is_active or student.role != User.Role.STUDENT:
        raise ValidationError({"user_id": "Select an existing active student account."})

    member, created = CourseMember.objects.get_or_create(
        course=course,
        user=student,
        defaults={"role": CourseMember.Role.STUDENT, "status": CourseMember.Status.ACTIVE},
    )
    if member.role != CourseMember.Role.STUDENT:
        raise ValidationError({"user_id": "This account has a non-student membership."})
    if not created and (
        member.status != CourseMember.Status.ACTIVE or member.removed_at is not None
    ):
        member.status = CourseMember.Status.ACTIVE
        member.removed_at = None
        member.full_clean()
        member.save(update_fields=["status", "removed_at"])
    return member, created


@transaction.atomic
def revoke_student_access(*, actor, course, member_id):
    course = Course.objects.select_for_update().get(pk=course.pk)
    if not can_manage_course(actor, course):
        raise PermissionDenied("You cannot manage this course.")

    member = CourseMember.objects.select_for_update().filter(
        pk=member_id, course=course
    ).first()
    if member is None:
        raise CourseMember.DoesNotExist("Membership not found in this course.")
    if member.role != CourseMember.Role.STUDENT:
        raise ValidationError({"member_id": "Only student memberships can be revoked."})
    if member.status != CourseMember.Status.REMOVED or member.removed_at is None:
        member.status = CourseMember.Status.REMOVED
        member.removed_at = timezone.now()
        member.full_clean()
        member.save(update_fields=["status", "removed_at"])
    return member
