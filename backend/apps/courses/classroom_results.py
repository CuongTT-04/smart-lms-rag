from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .assessment_models import Assessment, AssessmentAttempt
from .assessment_reports import local_date, make_xlsx
from .models import Classroom, Enrollment
from .permissions import can_manage_course, can_view_classroom
from .progress_services import bulk_enrollment_progress

SUBMISSION_STATUSES = ('NOT_SUBMITTED', 'DRAFT', 'SUBMITTED')
GRADING_STATUSES = ('NOT_APPLICABLE', 'PENDING', 'GRADED')


def validate_result_filters(params):
    allowed = {'q', 'submission_status', 'grading_status', 'page'}
    unexpected = set(params.keys()) - allowed
    if unexpected:
        raise ValidationError({field: ['Tham số lọc không được hỗ trợ.'] for field in sorted(unexpected)})
    q = str(params.get('q', '') or '').strip()[:255]
    submission_status = str(params.get('submission_status', '') or '').strip()
    grading_status = str(params.get('grading_status', '') or '').strip()
    if submission_status and submission_status not in SUBMISSION_STATUSES:
        raise ValidationError({'submission_status': ['Trạng thái nộp bài không hợp lệ.']})
    if grading_status and grading_status not in GRADING_STATUSES:
        raise ValidationError({'grading_status': ['Trạng thái chấm điểm không hợp lệ.']})
    return {'q': q, 'submission_status': submission_status, 'grading_status': grading_status}


def _attempt_sort_key(attempt):
    return (
        float(attempt.score),
        attempt.submitted_at or attempt.started_at,
        str(attempt.pk),
    )


def _latest_attempt_sort_key(attempt):
    return (
        attempt.submitted_at or attempt.started_at,
        attempt.number,
        str(attempt.pk),
    )


def _visible_graded_attempts(assessment, submitted_attempts, manager):
    if manager:
        return [attempt for attempt in submitted_attempts if attempt.score is not None]
    return [
        attempt
        for attempt in submitted_attempts
        if attempt.score is not None and (assessment.results_published or attempt.grade_published)
    ]


def _assessment_cell(assessment, attempts_for_student, manager, now):
    submitted = [attempt for attempt in attempts_for_student if attempt.status == 'SUBMITTED']
    drafts = [attempt for attempt in attempts_for_student if attempt.status == 'DRAFT']

    if submitted:
        submission_status = 'SUBMITTED'
    elif drafts:
        submission_status = 'DRAFT'
    else:
        submission_status = 'NOT_SUBMITTED'

    visible_graded = _visible_graded_attempts(assessment, submitted, manager)
    if assessment.mode == 'PRACTICE':
        selected = max(visible_graded, key=_attempt_sort_key) if visible_graded else None
    else:
        selected = visible_graded[0] if len(visible_graded) == 1 else (max(visible_graded, key=_attempt_sort_key) if visible_graded else None)

    latest_submitted = max(submitted, key=_latest_attempt_sort_key) if submitted else None
    if manager:
        pending_attempts_count = sum(1 for attempt in submitted if attempt.score is None)
    else:
        pending_attempts_count = sum(
            1 for attempt in submitted if attempt.score is None or not (assessment.results_published or attempt.grade_published)
        )

    if submission_status != 'SUBMITTED':
        grading_status = 'NOT_APPLICABLE'
    elif selected is not None:
        grading_status = 'GRADED'
    else:
        grading_status = 'PENDING'

    score = float(selected.score) if selected is not None else None
    is_overdue = bool(now >= assessment.due_at and submission_status != 'SUBMITTED')

    return {
        'assessment_id': str(assessment.pk),
        'title': assessment.title,
        'mode': assessment.mode,
        'kind': assessment.kind,
        'is_removed': bool(assessment.removed_at is not None or assessment.session.removed_at is not None),
        'is_overdue': is_overdue,
        'submission_status': submission_status,
        'grading_status': grading_status,
        'has_pending_grading': pending_attempts_count > 0,
        'score': score,
        'score_policy': 'HIGHEST_SUBMITTED' if assessment.mode == 'PRACTICE' else 'SINGLE_ATTEMPT',
        'attempt_count': len(attempts_for_student),
        'submitted_attempts_count': len(submitted),
        'pending_attempts_count': pending_attempts_count,
        'submitted_at': latest_submitted.submitted_at.isoformat() if latest_submitted and latest_submitted.submitted_at else None,
    }


def classroom_results(*, actor, classroom_id, filters):
    classroom = (
        Classroom.objects.select_related('course')
        .filter(pk=classroom_id, removed_at__isnull=True)
        .first()
    )
    if not classroom or not can_view_classroom(actor, classroom):
        raise NotFound('Lớp học không khả dụng.')

    manager = can_manage_course(actor, classroom.course)
    enrollments_qs = (
        Enrollment.objects.filter(
            classroom=classroom,
            status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
            student__user__is_active=True,
            student__user__course_memberships__course=classroom.course,
            student__user__course_memberships__status='ACTIVE',
        )
        .select_related('student__user')
        .distinct()
    )
    if not manager:
        enrollments_qs = enrollments_qs.filter(student__user=actor)
    enrollments = list(enrollments_qs)
    if not manager and not enrollments:
        raise NotFound('Không tìm thấy dữ liệu kết quả lớp học.')

    active_assessments = list(
        Assessment.objects.select_related('session')
        .filter(
            session__classroom=classroom,
            session__removed_at__isnull=True,
            session__is_draft=False,
            removed_at__isnull=True,
            is_published=True,
        )
        .order_by('session__position', 'created_at', 'id')
    )
    user_ids = [enrollment.student.user_id for enrollment in enrollments]
    removed_with_attempts = []
    if user_ids:
        removed_with_attempts = list(
            Assessment.objects.select_related('session')
            .filter(
                session__classroom=classroom,
                attempts__student_id__in=user_ids,
            )
            .filter(Q(removed_at__isnull=False) | Q(session__removed_at__isnull=False))
            .distinct()
            .order_by('created_at', 'id')
        )
    all_assessments = active_assessments + [a for a in removed_with_attempts if a.pk not in {x.pk for x in active_assessments}]
    assessment_ids = [assessment.pk for assessment in all_assessments]

    attempts_by_key = {}
    if user_ids and assessment_ids:
        for attempt in AssessmentAttempt.objects.filter(
            assessment_id__in=assessment_ids,
            student_id__in=user_ids,
        ).order_by('assessment_id', 'student_id', '-started_at', '-id'):
            attempts_by_key.setdefault((attempt.student_id, attempt.assessment_id), []).append(attempt)

    progress_by_enrollment = bulk_enrollment_progress(enrollments, classroom.pk)
    now = timezone.now()
    search_term = filters['q'].casefold()
    sub_filter = filters['submission_status']
    grade_filter = filters['grading_status']

    rows = []
    for enrollment in enrollments:
        user = enrollment.student.user
        name = user.full_name or user.username
        if search_term and search_term not in f'{name} {user.username}'.casefold():
            continue

        active_cells = []
        removed_cells = []
        for assessment in all_assessments:
            cell = _assessment_cell(
                assessment,
                attempts_by_key.get((user.pk, assessment.pk), []),
                manager,
                now,
            )
            if cell['is_removed']:
                removed_cells.append(cell)
            else:
                active_cells.append(cell)

        if sub_filter and not any(cell['submission_status'] == sub_filter for cell in active_cells):
            continue
        if grade_filter:
            if grade_filter == 'PENDING':
                if not any(cell['grading_status'] == 'PENDING' or cell['has_pending_grading'] for cell in active_cells):
                    continue
            elif not any(cell['grading_status'] == grade_filter for cell in active_cells):
                continue

        submitted_count = sum(1 for cell in active_cells if cell['submission_status'] == 'SUBMITTED')
        draft_count = sum(1 for cell in active_cells if cell['submission_status'] == 'DRAFT')
        not_submitted_count = sum(1 for cell in active_cells if cell['submission_status'] == 'NOT_SUBMITTED')
        pending_grading_count = sum(1 for cell in active_cells if cell['has_pending_grading'])
        pending_attempts_total = sum(cell['pending_attempts_count'] for cell in active_cells)
        graded_count = sum(1 for cell in active_cells if cell['grading_status'] == 'GRADED')
        overdue_count = sum(1 for cell in active_cells if cell['is_overdue'])
        visible_scores = [cell['score'] for cell in active_cells if cell['score'] is not None]
        average_score = round(sum(visible_scores) / len(visible_scores), 2) if visible_scores else None
        progress = progress_by_enrollment[enrollment.pk]

        rows.append({
            'student_id': str(user.pk),
            'name': name,
            'username': user.username,
            'enrollment_status': enrollment.status,
            'progress': progress,
            'submitted_count': submitted_count,
            'draft_count': draft_count,
            'not_submitted_count': not_submitted_count,
            'pending_grading_count': pending_grading_count,
            'pending_attempts_count': pending_attempts_total,
            'graded_count': graded_count,
            'overdue_count': overdue_count,
            'average_score': average_score,
            'assessments': active_cells + removed_cells,
        })

    rows.sort(key=lambda row: (row['name'].casefold(), row['student_id']))
    row_averages = [row['average_score'] for row in rows if row['average_score'] is not None]

    assessment_headers = [
        {
            'id': str(assessment.pk),
            'title': assessment.title,
            'mode': assessment.mode,
            'kind': assessment.kind,
            'due_at': assessment.due_at.isoformat(),
            'is_overdue': bool(now >= assessment.due_at),
            'is_removed': bool(assessment.removed_at is not None or assessment.session.removed_at is not None),
        }
        for assessment in all_assessments
    ]

    return {
        'classroom_id': str(classroom.pk),
        'classroom_name': classroom.name,
        'viewer_role': 'TEACHER' if manager else 'STUDENT',
        'score_policy': {
            'practice': 'HIGHEST_SUBMITTED',
            'test': 'SINGLE_ATTEMPT',
            'average_scope': 'VISIBLE_GRADED_ONLY',
        },
        'filters': filters,
        'assessments': assessment_headers,
        'summary': {
            'student_count': len(rows),
            'active_assessment_count': len(active_assessments),
            'removed_assessment_count': len(all_assessments) - len(active_assessments),
            'submitted_cells': sum(row['submitted_count'] for row in rows),
            'draft_cells': sum(row['draft_count'] for row in rows),
            'not_submitted_cells': sum(row['not_submitted_count'] for row in rows),
            'pending_grading_cells': sum(row['pending_grading_count'] for row in rows),
            'pending_attempts': sum(row['pending_attempts_count'] for row in rows),
            'average_score': round(sum(row_averages) / len(row_averages), 2) if row_averages else None,
        },
        'rows': rows,
    }


def export_classroom_results_workbook(report):
    meta = [
        ['Bảng kết quả lớp học', report['classroom_name']],
        ['Xuất lúc', local_date(timezone.now())],
        ['Chính sách điểm', 'Ôn tập: điểm cao nhất đã nộp/công bố · Kiểm tra: lượt duy nhất'],
        ['Bộ lọc', str(report['filters'])],
    ]
    headers = ['Học viên', 'Tài khoản', 'Tiến độ (%)', 'Đã nộp', 'Chưa nộp', 'Bài chờ chấm', 'Lượt chờ chấm', 'Điểm TB']
    for item in report['assessments']:
        suffix = ' [Đã gỡ]' if item['is_removed'] else (' [Quá hạn]' if item['is_overdue'] else '')
        headers.append(f"{item['title']}{suffix}")
    rows = [headers]
    status_labels = {'NOT_SUBMITTED': 'Chưa nộp', 'DRAFT': 'Đang làm', 'SUBMITTED': 'Chờ chấm'}
    for student in report['rows']:
        line = [
            student['name'],
            student['username'],
            student['progress']['percent'],
            student['submitted_count'],
            student['not_submitted_count'],
            student['pending_grading_count'],
            student['pending_attempts_count'],
            student['average_score'],
        ]
        cells_by_id = {cell['assessment_id']: cell for cell in student['assessments']}
        for item in report['assessments']:
            cell = cells_by_id.get(item['id'])
            if not cell:
                line.append('')
            elif cell['score'] is not None:
                line.append(cell['score'])
            else:
                line.append(status_labels.get(cell['submission_status'], cell['submission_status']))
        rows.append(line)
    summary_rows = meta + [
        ['Chỉ số tổng hợp', 'Giá trị'],
        ['Số học viên', report['summary']['student_count']],
        ['Số bài áp dụng', report['summary']['active_assessment_count']],
        ['Lượt bài đã nộp', report['summary']['submitted_cells']],
        ['Lượt bài chưa nộp', report['summary']['not_submitted_cells']],
        ['Bài có lượt chờ chấm', report['summary']['pending_grading_cells']],
        ['Tổng lượt chờ chấm', report['summary']['pending_attempts']],
        ['Điểm trung bình lớp', report['summary']['average_score']],
    ]
    return make_xlsx([('Kết quả lớp học', meta + rows), ('Tổng hợp', summary_rows)])
