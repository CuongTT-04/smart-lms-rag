from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.documents.models import DocumentVersion, KnowledgeDocument
from .assessment_models import Assessment, AssessmentAttempt
from .models import Classroom, ClassroomSession, Course, CourseMember, Enrollment
from .permissions import can_manage_course, can_view_classroom
from .progress_models import DocumentCompletion
from .video_models import SessionVideo, VideoProgress, VideoQuestion


def _classroom_activities(classroom_id):
    sessions = list(
        ClassroomSession.objects.filter(
            classroom_id=classroom_id,
            removed_at__isnull=True,
            is_draft=False,
        ).order_by('position', 'created_at', 'id')
    )
    session_ids = [session.pk for session in sessions]
    if not session_ids:
        return sessions, [], [], [], {}
    documents = list(
        KnowledgeDocument.objects.filter(
            session_id__in=session_ids,
            removed_at__isnull=True,
            is_published=True,
            published_version__isnull=False,
            published_version__removed_at__isnull=True,
        ).order_by('created_at', 'id')
    )
    videos = list(
        SessionVideo.objects.filter(
            session_id__in=session_ids,
            removed_at__isnull=True,
            is_published=True,
        ).order_by('created_at', 'id')
    )
    assessments = list(
        Assessment.objects.filter(
            session_id__in=session_ids,
            removed_at__isnull=True,
            is_published=True,
        ).order_by('created_at', 'id')
    )
    video_ids = [video.pk for video in videos]
    questions_by_video = {}
    if video_ids:
        for q_id, v_id, revision in VideoQuestion.objects.filter(
            video_id__in=video_ids,
            removed_at__isnull=True,
        ).values_list('id', 'video_id', 'revision'):
            questions_by_video.setdefault(v_id, []).append((str(q_id), revision))
    return sessions, documents, videos, assessments, questions_by_video


def _completion_sets(enrollments, documents, videos, assessments, questions_by_video):
    if not enrollments:
        return {}, {}, {}
    enrollment_ids = [enrollment.pk for enrollment in enrollments]
    user_ids = list({enrollment.student.user_id for enrollment in enrollments})
    version_ids = [doc.published_version_id for doc in documents]
    video_ids = [video.pk for video in videos]
    assessment_ids = [assessment.pk for assessment in assessments]

    completed_docs = {}
    if version_ids:
        for enrollment_id, version_id in DocumentCompletion.objects.filter(
            enrollment_id__in=enrollment_ids,
            document_version_id__in=version_ids,
        ).values_list('enrollment_id', 'document_version_id'):
            completed_docs.setdefault(enrollment_id, set()).add(version_id)

    completed_videos = {}
    if video_ids:
        for student_id, video_id, passed in VideoProgress.objects.filter(
            video_id__in=video_ids,
            student_id__in=user_ids,
            completed_at__isnull=False,
        ).values_list('student_id', 'video_id', 'passed'):
            passed_map = passed if isinstance(passed, dict) else {}
            required = questions_by_video.get(video_id, ())
            if all(passed_map.get(q_id) == rev for q_id, rev in required):
                completed_videos.setdefault(student_id, set()).add(video_id)

    completed_assessments = {}
    if assessment_ids:
        for student_id, assessment_id in (
            AssessmentAttempt.objects.filter(
                assessment_id__in=assessment_ids,
                student_id__in=user_ids,
                status='SUBMITTED',
            )
            .values_list('student_id', 'assessment_id')
            .distinct()
        ):
            completed_assessments.setdefault(student_id, set()).add(assessment_id)

    return completed_docs, completed_videos, completed_assessments


def bulk_enrollment_progress(enrollments, classroom_id):
    """Compute live progress metrics {enrollment_id: summary_dict} in O(1) queries."""
    if not enrollments:
        return {}
    _, documents, videos, assessments, questions_by_video = _classroom_activities(classroom_id)
    total = len(documents) + len(videos) + len(assessments)
    completed_docs, completed_videos, completed_assessments = _completion_sets(
        enrollments, documents, videos, assessments, questions_by_video
    )
    summaries = {}
    for enrollment in enrollments:
        if total == 0:
            summaries[enrollment.pk] = {
                'total_activities': 0,
                'completed_activities': 0,
                'percent': 0.0,
                'has_activities': False,
                'completed_at': None,
            }
            continue
        doc_done = completed_docs.get(enrollment.pk, set())
        vid_done = completed_videos.get(enrollment.student.user_id, set())
        assess_done = completed_assessments.get(enrollment.student.user_id, set())
        done_count = (
            sum(1 for doc in documents if doc.published_version_id in doc_done)
            + sum(1 for vid in videos if vid.pk in vid_done)
            + sum(1 for ass in assessments if ass.pk in assess_done)
        )
        is_complete = done_count == total
        summaries[enrollment.pk] = {
            'total_activities': total,
            'completed_activities': done_count,
            'percent': round(done_count / total * 100, 2),
            'has_activities': True,
            'completed_at': enrollment.completed_at if is_complete else None,
        }
    return summaries


def _sync_enrollments(enrollments, classroom_id):
    if not enrollments:
        return 0
    summaries = bulk_enrollment_progress(enrollments, classroom_id)
    now = timezone.now()
    updated = 0
    for enrollment in enrollments:
        if enrollment.status not in (Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED):
            continue
        summary = summaries[enrollment.pk]
        total = summary['total_activities']
        done = summary['completed_activities']
        new_percent = summary['percent']
        if total > 0 and done == total:
            new_status = Enrollment.Status.COMPLETED
            new_completed_at = enrollment.completed_at or now
        else:
            new_status = Enrollment.Status.ACTIVE
            new_completed_at = None
        if (
            enrollment.progress_percent != new_percent
            or enrollment.status != new_status
            or enrollment.completed_at != new_completed_at
        ):
            enrollment.progress_percent = new_percent
            enrollment.status = new_status
            enrollment.completed_at = new_completed_at
            enrollment.save(update_fields=['progress_percent', 'status', 'completed_at'])
            updated += 1
    return updated


def refresh_classroom_progress(*, classroom_id):
    with transaction.atomic():
        enrollments = list(
            Enrollment.objects.select_for_update()
            .select_related('student')
            .filter(
                classroom_id=classroom_id,
                status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
            )
            .order_by('pk')
        )
        return _sync_enrollments(enrollments, classroom_id)


def _student_classroom_and_enrollment(actor, classroom_id, *, lock=False):
    classroom = (
        Classroom.objects.select_related('course')
        .filter(pk=classroom_id, removed_at__isnull=True)
        .first()
    )
    if not classroom or not can_view_classroom(actor, classroom):
        raise NotFound('Lớp học không khả dụng.')
    if can_manage_course(actor, classroom.course):
        raise PermissionDenied('Giáo viên sử dụng kết quả lớp thay cho tiến độ học viên.')
    query = Enrollment.objects.select_related('student').filter(
        classroom=classroom,
        student__user=actor,
        status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
    )
    if lock:
        query = query.select_for_update()
    enrollment = query.first()
    if enrollment is None:
        raise NotFound('Không tìm thấy ghi danh hợp lệ.')
    return classroom, enrollment


def _build_progress_payload(classroom, enrollment):
    sessions, documents, videos, assessments, questions_by_video = _classroom_activities(classroom.pk)
    completed_docs, completed_videos, completed_assessments = _completion_sets(
        [enrollment], documents, videos, assessments, questions_by_video
    )
    doc_done = completed_docs.get(enrollment.pk, set())
    vid_done = completed_videos.get(enrollment.student.user_id, set())
    assess_done = completed_assessments.get(enrollment.student.user_id, set())

    docs_by_session = {}
    for doc in documents:
        docs_by_session.setdefault(doc.session_id, []).append(doc)
    videos_by_session = {}
    for video in videos:
        videos_by_session.setdefault(video.session_id, []).append(video)
    assessments_by_session = {}
    for assessment in assessments:
        assessments_by_session.setdefault(assessment.session_id, []).append(assessment)

    session_rows = []
    total_activities = 0
    completed_activities = 0
    for session in sessions:
        activities = []
        for doc in docs_by_session.get(session.pk, ()):
            done = doc.published_version_id in doc_done
            activities.append({
                'kind': 'PDF',
                'id': str(doc.pk),
                'version_id': str(doc.published_version_id),
                'title': doc.title,
                'completed': done,
            })
        for video in videos_by_session.get(session.pk, ()):
            done = video.pk in vid_done
            activities.append({
                'kind': 'VIDEO',
                'id': str(video.pk),
                'title': video.title,
                'completed': done,
            })
        for assessment in assessments_by_session.get(session.pk, ()):
            done = assessment.pk in assess_done
            activities.append({
                'kind': 'ASSESSMENT',
                'id': str(assessment.pk),
                'title': assessment.title,
                'completed': done,
            })
        session_total = len(activities)
        session_done = sum(1 for item in activities if item['completed'])
        total_activities += session_total
        completed_activities += session_done
        session_rows.append({
            'session_id': str(session.pk),
            'title': session.title,
            'position': session.position,
            'total_activities': session_total,
            'completed_activities': session_done,
            'activities': activities,
        })

    if total_activities == 0:
        percent = 0.0
        has_activities = False
        completed_at = None
    else:
        has_activities = True
        percent = round(completed_activities / total_activities * 100, 2)
        completed_at = (
            enrollment.completed_at.isoformat()
            if completed_activities == total_activities and enrollment.completed_at is not None
            else None
        )

    return {
        'classroom_id': str(classroom.pk),
        'total_activities': total_activities,
        'completed_activities': completed_activities,
        'percent': percent,
        'has_activities': has_activities,
        'completed_at': completed_at,
        'sessions': session_rows,
    }


def classroom_progress(*, actor, classroom_id):
    classroom, enrollment = _student_classroom_and_enrollment(actor, classroom_id, lock=False)
    return _build_progress_payload(classroom, enrollment)


def mark_document_complete(*, actor, classroom_id, version_id):
    with transaction.atomic():
        classroom, enrollment = _student_classroom_and_enrollment(actor, classroom_id, lock=True)
        # Re-check active membership and course state inside the locked transaction.
        member_active = CourseMember.objects.filter(
            course_id=classroom.course_id,
            user_id=actor.pk,
            role=CourseMember.Role.STUDENT,
            status=CourseMember.Status.ACTIVE,
        ).exists()
        course_published = Course.objects.filter(
            pk=classroom.course_id,
            status=Course.Status.PUBLISHED,
        ).exists()
        if not member_active or not course_published:
            raise NotFound('Lớp học không khả dụng.')
        version = (
            DocumentVersion.objects.select_for_update()
            .select_related('document', 'document__session')
            .filter(
                pk=version_id,
                removed_at__isnull=True,
                document__removed_at__isnull=True,
                document__is_published=True,
                document__published_version_id=version_id,
                document__session__classroom_id=classroom.pk,
                document__session__removed_at__isnull=True,
                document__session__is_draft=False,
            )
            .first()
        )
        if version is None:
            raise NotFound('Tài liệu không khả dụng hoặc chưa được công bố trong lớp này.')
        try:
            DocumentCompletion.objects.get_or_create(
                enrollment=enrollment,
                document_version=version,
            )
        except IntegrityError:
            pass
        _sync_enrollments([enrollment], classroom.pk)
        return _build_progress_payload(classroom, enrollment)
