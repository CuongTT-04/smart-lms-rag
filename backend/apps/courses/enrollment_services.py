from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.users.models import StudentProfile, User
from .models import AccessPolicy, Classroom, Course, CourseMember, Enrollment, JoinRequest
from .permissions import can_manage_course


def active_student(user):
    return user.is_active and user.status == User.Status.ACTIVE and user.role == User.Role.STUDENT


def locked_course(actor, course):
    course = Course.objects.select_for_update().get(pk=course.pk)
    actor = User.objects.get(pk=actor.pk)
    if actor.status != User.Status.ACTIVE or not can_manage_course(actor, course):
        raise PermissionDenied("Only the active course owner can manage enrollment.")
    return course


def check_joinable(course, classroom):
    policy = AccessPolicy.objects.get(course=course)
    owner = course.memberships.filter(role="OWNER", status="ACTIVE", user__role="TEACHER", user__is_active=True, user__status="ACTIVE").exists()
    if not owner or classroom.removed_at or course.status != Course.Status.PUBLISHED or not classroom.is_join_enabled:
        raise ValidationError({"class_code": ["This classroom is not accepting enrollment."]})
    if policy.access_type != AccessPolicy.AccessType.FREE or policy.price != 0:
        raise ValidationError({"class_code": ["Only free courses support joining by class code."]})
    return policy


def activate(course, classroom, student):
    member, _ = CourseMember.objects.get_or_create(course=course, user=student, defaults={"role": "STUDENT"})
    if member.role != "STUDENT":
        raise ValidationError({"student": ["A non-student membership cannot be replaced."]})
    if member.status != "ACTIVE":
        member.status = "ACTIVE"
        member.removed_at = None
        member.joined_at = timezone.now()
        member.save(update_fields=["status", "removed_at", "joined_at"])
    profile, _ = StudentProfile.objects.get_or_create(user=student)
    enrollment, _ = Enrollment.objects.get_or_create(classroom=classroom, student=profile)
    if enrollment.status == Enrollment.Status.WITHDRAWN:
        enrollment.status = Enrollment.Status.ACTIVE
        enrollment.enrolled_at = timezone.now()
        enrollment.save(update_fields=["status", "enrolled_at"])
    return enrollment


@transaction.atomic
def join_by_code(*, actor, class_code, message=""):
    classroom = Classroom.objects.filter(class_code=class_code.upper()).first()
    if classroom is None:
        raise ValidationError({"class_code": ["Invalid class code."]})
    course = Course.objects.select_for_update().get(pk=classroom.course_id)
    classroom.refresh_from_db()
    actor = User.objects.select_for_update().get(pk=actor.pk)
    if not active_student(actor):
        raise PermissionDenied("Only active students can join classrooms.")
    policy = check_joinable(course, classroom)
    member = CourseMember.objects.filter(course=course, user=actor).first()
    if member and member.role != "STUDENT":
        raise PermissionDenied("This account has a non-student membership.")
    enrollment = Enrollment.objects.filter(classroom=classroom, student__user=actor).first()
    if member and member.status == "ACTIVE" and enrollment and enrollment.status != Enrollment.Status.WITHDRAWN:
        return "ENROLLED", enrollment, False
    pending = JoinRequest.objects.filter(classroom=classroom, student=actor, status="PENDING").first()
    if pending:
        return "PENDING", pending, False
    if classroom.require_approval or (member and member.status != "ACTIVE") or (enrollment and enrollment.status == Enrollment.Status.WITHDRAWN):
        request = JoinRequest.objects.create(classroom=classroom, student=actor, message=message)
        return "PENDING", request, True
    return "ENROLLED", activate(course, classroom, actor), True


@transaction.atomic
def review_request(*, actor, course, request_id, decision, review_note=""):
    course = locked_course(actor, course)
    if decision not in {"approve", "reject"}:
        raise ValidationError({"decision": ["Select approve or reject."]})
    request = JoinRequest.objects.select_for_update().select_related("classroom").filter(pk=request_id, classroom__course=course).first()
    if request is None:
        raise JoinRequest.DoesNotExist
    target_status = "APPROVED" if decision == "approve" else "REJECTED"
    if request.status != "PENDING":
        if request.status == target_status:
            return request
        raise ValidationError({"status": ["This request has already been processed."]})
    if decision == "approve":
        check_joinable(course, request.classroom)
        student = User.objects.select_for_update().get(pk=request.student_id)
        if not active_student(student):
            raise ValidationError({"student": ["The applicant is no longer an active student."]})
        activate(course, request.classroom, student)
    request.status = target_status
    request.reviewed_by = actor
    request.review_note = review_note
    request.reviewed_at = timezone.now()
    request.save()
    return request


@transaction.atomic
def cancel_request(*, actor, request_id):
    existing = JoinRequest.objects.filter(pk=request_id, student=actor).first()
    if existing is None:
        raise JoinRequest.DoesNotExist
    Course.objects.select_for_update().get(pk=existing.classroom.course_id)
    request = JoinRequest.objects.select_for_update().get(pk=existing.pk)
    if request.status == "CANCELED":
        return request
    if request.status != "PENDING":
        raise ValidationError({"status": ["Only pending requests can be canceled."]})
    request.status = "CANCELED"
    request.save(update_fields=["status", "updated_at"])
    return request


@transaction.atomic
def save_policy(*, actor, course, changes):
    course = locked_course(actor, course)
    if not changes or set(changes) - {"require_approval", "visibility"}:
        raise ValidationError({"policy": ["Only require_approval and visibility can be updated."]})
    policy = AccessPolicy.objects.get(course=course)
    for field, value in changes.items():
        setattr(policy, field, value)
    policy.full_clean()
    policy.save()
    return policy


@transaction.atomic
def save_classroom(*, actor, course, changes, classroom_id=None):
    course = locked_course(actor, course)
    if not changes or set(changes) - {"name", "is_join_enabled", "visibility", "require_approval"}:
        raise ValidationError({"classroom": ["Only classroom name, visibility, approval and registration settings can be updated."]})
    if classroom_id:
        classroom = Classroom.objects.filter(pk=classroom_id, course=course).first()
        if classroom is None:
            raise Classroom.DoesNotExist
    else:
        classroom = Classroom(course=course)
    for field, value in changes.items():
        setattr(classroom, field, value)
    classroom.full_clean()
    classroom.save()
    return classroom


@transaction.atomic
def remove_classroom(*, actor, course, classroom_id):
    from apps.documents.services import remove_document
    course = locked_course(actor, course)
    classroom = Classroom.objects.select_for_update().filter(pk=classroom_id, course=course).first()
    if classroom is None:
        raise Classroom.DoesNotExist
    now = timezone.now()
    for session in classroom.sessions.select_for_update().filter(removed_at__isnull=True).order_by('pk'):
        for material in session.materials.filter(removed_at__isnull=True).order_by('pk'):
            remove_document(actor, material)
        session.removed_at = now
        session.save(update_fields=['removed_at'])
    classroom.enrollments.exclude(status=Enrollment.Status.WITHDRAWN).update(status=Enrollment.Status.WITHDRAWN)
    classroom.join_requests.filter(status='PENDING').update(status='CANCELED', updated_at=now)
    classroom.removed_at = now
    classroom.is_join_enabled = False
    classroom.save(update_fields=['removed_at', 'is_join_enabled', 'updated_at'])


@transaction.atomic
def withdraw_classroom_enrollment(*, actor, course, classroom_id, enrollment_id):
    course = locked_course(actor, course)
    if not Classroom.objects.filter(pk=classroom_id, course=course).exists():
        raise Classroom.DoesNotExist
    enrollment = Enrollment.objects.select_for_update().filter(
        pk=enrollment_id, classroom_id=classroom_id
    ).select_related("student").first()
    if enrollment is None:
        raise Enrollment.DoesNotExist
    member = CourseMember.objects.select_for_update().filter(
        course=course, user_id=enrollment.student.user_id
    ).first()
    if member and member.role != CourseMember.Role.STUDENT:
        raise ValidationError({"enrollment_id": ["A non-student membership cannot be revoked."]})
    if enrollment.status != Enrollment.Status.WITHDRAWN:
        enrollment.status = Enrollment.Status.WITHDRAWN
        enrollment.save(update_fields=["status"])
    # Course-level access survives while another classroom enrollment is effective.
    has_other_classroom = Enrollment.objects.filter(
        classroom__course=course, student=enrollment.student
    ).exclude(status=Enrollment.Status.WITHDRAWN).exists()
    if not has_other_classroom and member and (
        member.status != CourseMember.Status.REMOVED or member.removed_at is None
    ):
        member.status = CourseMember.Status.REMOVED
        member.removed_at = timezone.now()
        member.save(update_fields=["status", "removed_at"])
    return enrollment
