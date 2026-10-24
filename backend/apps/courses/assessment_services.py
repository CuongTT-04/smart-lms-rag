import uuid
import logging
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from rest_framework.exceptions import ValidationError, APIException
from .assessment_models import AssessmentAttempt
from .assessment_questions import correct_ids, selected_ids, is_correct


class DraftConflict(APIException):
    status_code = 409
    default_detail = 'Bài làm đã thay đổi ở một cửa sổ khác. Hãy tải lại trước khi sửa tiếp.'


def finalize(attempt, automatic=False):
    if attempt.status == 'SUBMITTED':
        return
    assessment = attempt.assessment
    attempt.status = 'SUBMITTED'
    attempt.submitted_at = min(timezone.now(), attempt.expires_at) if automatic else timezone.now()
    attempt.auto_submitted = automatic
    if assessment.kind == 'QUIZ':
        correct = sum(is_correct(q, attempt.answers.get(q['id'])) for q in assessment.questions)
        attempt.score = (Decimal(correct) * 10 / len(assessment.questions)).quantize(Decimal('.01'))
    attempt.save()


def expire(attempt):
    if attempt.assessment.kind == 'QUIZ' and attempt.status == 'DRAFT' and timezone.now() >= min(attempt.expires_at, attempt.assessment.due_at):
        finalize(attempt, automatic=True)


def start_attempt(assessment, student, values):
    now = timezone.now()
    previous = assessment.attempts.filter(student=student)
    active = previous.filter(status='DRAFT').first()
    if active:
        expire(active)
        if active.status == 'DRAFT':
            if assessment.mode == 'TEST' and not values['fullscreen']:
                raise ValidationError('Cần vào toàn màn hình trước khi tiếp tục bài kiểm tra.')
            return active
    same = previous.filter(request_id=values['request_id']).first()
    if same:
        return same
    if now >= assessment.due_at:
        raise ValidationError('Đã hết hạn nhận bài.')
    if assessment.mode == 'TEST':
        if previous.exists():
            raise ValidationError('Bài kiểm tra chỉ cho phép một lượt làm/nộp.')
        if not values['fullscreen']:
            raise ValidationError('Cần vào toàn màn hình trước khi bắt đầu bài kiểm tra.')
    expires = min(assessment.due_at, now + timedelta(seconds=assessment.duration_seconds)) if assessment.kind == 'QUIZ' else assessment.due_at
    latest = previous.first()
    copied = {}
    if latest and assessment.kind == 'TEXT' and assessment.mode == 'PRACTICE':
        copied = {'text': latest.text, 'file': latest.file.name, 'file_name': latest.file_name, 'file_type': latest.file_type}
    return AssessmentAttempt.objects.create(assessment=assessment, student=student, request_id=values['request_id'], number=(latest.number if latest else 0)+1, expires_at=expires, **copied)


def validate_upload(file):
    if not 0 < file.size <= 20 * 1024 * 1024:
        raise ValidationError('Tệp phải có dung lượng từ 1 byte đến 20 MiB.')
    header = file.read(16)
    file.seek(0)
    suffix = file.name.lower().rsplit('.', 1)[-1]
    if suffix == 'pdf' and header.startswith(b'%PDF-'):
        return 'application/pdf', 'pdf'
    from PIL import Image
    try:
        image = Image.open(file)
        fmt = image.format
        if image.width * image.height > 20000000:
            raise ValueError('Ảnh quá lớn')
        image.verify()
        if fmt == 'PNG' and suffix == 'png':
            return 'image/png', 'png'
        if fmt == 'JPEG' and suffix in ['jpg', 'jpeg']:
            return 'image/jpeg', 'jpg'
    except Exception:
        pass
    finally:
        file.seek(0)
    raise ValidationError('Chỉ nhận tệp PDF hoặc ảnh PNG/JPEG hợp lệ.')


def save_draft(attempt, values):
    expire(attempt)
    if attempt.status != 'DRAFT':
        raise ValidationError('Bài đã nộp, không thể chỉnh sửa lượt này.')
    if timezone.now() >= min(attempt.expires_at, attempt.assessment.due_at):
        raise ValidationError('Đã hết hạn chỉnh sửa bài.')
    if values['revision'] != attempt.revision:
        raise DraftConflict()
    assessment = attempt.assessment
    old_file = attempt.file.name
    new_file = None
    storage = attempt.file.storage
    if assessment.kind == 'QUIZ':
        if any(k in values for k in ['text', 'file']) or values.get('remove_file'):
            raise ValidationError('Quiz chỉ nhận lựa chọn câu trả lời.')
        answers = values.get('answers', attempt.answers)
        valid = {q['id']: q for q in assessment.questions}
        for key, value in answers.items():
            q = valid.get(key)
            if q is None or not isinstance(value, list if q.get('multiple', False) else str):
                raise ValidationError('Kiểu câu trả lời không đúng loại câu hỏi.')
            picked = selected_ids(value)
            if len(picked) > 8 or any(not isinstance(v, str) or len(v) > 64 for v in picked) or len(set(picked)) != len(picked) or not set(picked).issubset({c['id'] for c in q['choices']}):
                raise ValidationError('Câu hỏi hoặc lựa chọn không thuộc đề.')
        attempt.answers = answers
    else:
        if 'answers' in values:
            raise ValidationError('Bài tự luận chỉ nhận văn bản hoặc tệp.')
        attempt.text = values.get('text', attempt.text)
        if values.get('remove_file'):
            attempt.file = ''; attempt.file_name = ''; attempt.file_type = ''
        file = values.get('file')
        if (file or (attempt.file and not values.get('remove_file'))) and attempt.text.strip():
            raise ValidationError('Chọn văn bản hoặc một tệp, không gửi cả hai.')
        if file:
            content_type, suffix = validate_upload(file)
            attempt.file.save(f'{uuid.uuid4().hex}.{suffix}', file, save=False)
            new_file = attempt.file.name
            attempt.file_name = file.name[:255]
            attempt.file_type = content_type
        if attempt.file and attempt.text.strip():
            raise ValidationError('Chọn văn bản hoặc một tệp, không gửi cả hai.')
    attempt.revision += 1
    try:
        attempt.save()
    except Exception:
        if new_file:
            storage.delete(new_file)
        raise
    if old_file and old_file != attempt.file.name:
        def clean_replaced():
            if not AssessmentAttempt.objects.filter(file=old_file).exists():
                try:
                    storage.delete(old_file)
                except OSError:
                    logging.getLogger(__name__).exception('Could not clean superseded assessment draft file')
        transaction.on_commit(clean_replaced)


def submit_attempt(attempt, values):
    expire(attempt)
    if attempt.status == 'SUBMITTED':
        return
    if timezone.now() >= min(attempt.expires_at, attempt.assessment.due_at):
        raise ValidationError('Đã hết hạn nộp bài.')
    if values['revision'] != attempt.revision:
        raise DraftConflict()
    if attempt.assessment.mode == 'TEST' and not values['confirmed']:
        raise ValidationError('Cần xác nhận nộp bài kiểm tra; không thể nộp lại.')
    if attempt.assessment.kind == 'TEXT' and not attempt.text.strip() and not attempt.file:
        raise ValidationError('Nhập bài làm hoặc chọn một tệp trước khi nộp.')
    finalize(attempt)


def question_output(assessment, manager=False, solutions=False):
    output = []
    for question in assessment.questions:
        q = {k: v for k, v in question.items() if k not in ['correct_id', 'correct_ids'] and (k != 'hint' or manager or assessment.mode == 'PRACTICE')}
        q['multiple'] = question.get('multiple', False)
        if manager or solutions:
            q['correct_ids'] = correct_ids(question)
        output.append(q)
    return output


def assessment_output(assessment, manager=False):
    return {'id': str(assessment.pk), 'title': assessment.title, 'description': assessment.description, 'kind': assessment.kind, 'mode': assessment.mode,
            'due_at': assessment.due_at, 'duration_seconds': assessment.duration_seconds, 'is_published': assessment.is_published,
            'results_published': assessment.results_published, 'solutions_published': assessment.solutions_published,
            'questions': question_output(assessment, manager), 'hint': assessment.hint if manager or assessment.mode == 'PRACTICE' else '',
            'ai_allowed': assessment.mode == 'PRACTICE', 'locked': assessment.attempts.exists() if manager else None, 'server_now': timezone.now()}


def attempt_output(attempt, manager=False):
    assessment = attempt.assessment
    visible = manager or (attempt.status == 'SUBMITTED' and (assessment.results_published or attempt.grade_published))
    solutions = attempt.status == 'SUBMITTED' and assessment.solutions_published and (assessment.mode == 'PRACTICE' or timezone.now() >= assessment.due_at)
    result = {'id': str(attempt.pk), 'number': attempt.number, 'status': attempt.status, 'revision': attempt.revision,
              'answers': attempt.answers, 'text': attempt.text, 'file_name': attempt.file_name,
              'started_at': attempt.started_at, 'expires_at': attempt.expires_at, 'submitted_at': attempt.submitted_at,
              'auto_submitted': attempt.auto_submitted, 'score': float(attempt.score) if visible and attempt.score is not None else None,
              'feedback': attempt.feedback if visible else '', 'grade_published': attempt.grade_published,
              'graded': attempt.score is not None if visible else False, 'server_now': timezone.now(),
              'questions': question_output(assessment, manager, solutions), 'violation_count': attempt.events.count()}
    if manager:
        result.update(student_id=str(attempt.student_id), student_name=attempt.student.full_name or attempt.student.username,
                      moderation_note=attempt.moderation_note,
                      events=list(attempt.events.values('event_id', 'kind', 'created_at')),
                      grade_history=list(attempt.grade_history.values('teacher_id', 'before', 'after', 'created_at')))
    return result
