import math
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from .video_models import VideoProgress, VideoAnswer


class VideoRevisionConflict(APIException):
    status_code = 409
    default_detail = 'Câu hỏi đã thay đổi. Vui lòng tải lại video.'


def active_questions(video):
    return video.questions.filter(removed_at__isnull=True)


def progress_for(video, user):
    progress, _ = VideoProgress.objects.get_or_create(video=video, student=user)
    return progress


def pending_question(video, progress):
    return next((question for question in active_questions(video) if progress.passed.get(str(question.pk)) != question.revision), None)


def progress_output(video, progress):
    question = pending_question(video, progress)
    passed = [str(q.pk) for q in active_questions(video) if progress.passed.get(str(q.pk)) == q.revision]
    ceiling = question.start_time if question else video.duration
    completed = progress.completed_at is not None and question is None
    frontier = progress.replay_position if progress.replay_position is not None else progress.watched_until
    return {'position': min(progress.position, ceiling), 'watched_until': progress.watched_until,
            'seekable_until': video.duration if completed else min(frontier, ceiling),
            'passed_ids': passed, 'completed': completed}


def update_progress(video, user, position):
    progress = progress_for(video, user)
    question = pending_question(video, progress)
    ceiling = question.start_time if question else video.duration
    if not math.isfinite(position) or position > ceiling + 0.05:
        raise ValidationError('Không được tua qua câu hỏi chưa hoàn thành.')
    elapsed = max(0, (timezone.now() - progress.updated_at).total_seconds())
    # Consume one shared allowance; repeated requests cannot mint playback time.
    credit = min(6, progress.playback_credit + elapsed)
    frontier = progress.replay_position if progress.replay_position is not None else progress.watched_until
    completed = progress.completed_at is not None and question is None
    advance = 0 if completed else max(0, position - frontier)
    if advance > credit:
        raise ValidationError('Không được tua tiến. Hãy tiếp tục xem từ vị trí đã lưu.')
    progress.playback_credit = credit - advance
    progress.position = min(position, ceiling, video.duration)
    progress.watched_until = max(progress.watched_until, progress.position)
    if progress.replay_position is not None:
        progress.replay_position = max(progress.replay_position, progress.position)
    if question is None and progress.watched_until >= video.duration - min(0.1, video.duration * 0.01) and progress.completed_at is None:
        progress.completed_at = timezone.now()
    progress.save(update_fields=['position', 'watched_until', 'replay_position', 'completed_at', 'playback_credit', 'updated_at'])
    return progress_output(video, progress)


def submit_answer(video, question, user, values):
    if values['revision'] != question.revision:
        raise VideoRevisionConflict()
    existing = VideoAnswer.objects.filter(video=video, student=user, request_id=values['request_id']).first()
    if existing:
        if existing.question_id != question.pk or existing.question_revision != values['revision'] or existing.selected_ids != values.get('selected_ids', []) or existing.text != values.get('text', ''):
            raise ValidationError('Mã yêu cầu đã được dùng cho nội dung khác.')
        return existing
    progress = progress_for(video, user)
    pending = pending_question(video, progress)
    if not pending or pending.pk != question.pk or progress.position < question.start_time - 0.5:
        raise ValidationError('Bạn cần xem đến đúng mốc câu hỏi trước khi trả lời.')
    selected = values.get('selected_ids', [])
    text = values.get('text', '')
    if question.kind == 'TEXT':
        if not text.strip() or selected:
            raise ValidationError('Nhập câu trả lời tự luận, không gửi lựa chọn trắc nghiệm.')
        correct = None
    else:
        if not selected or (not question.multiple and len(selected) != 1) or len(set(selected)) != len(selected) or not set(selected).issubset({item['id'] for item in question.choices}) or text:
            raise ValidationError('Chọn đáp án trắc nghiệm hợp lệ.')
        correct = set(selected) == set(question.correct_ids)
    rewind = question.rewind_time if correct is False else None
    answer = VideoAnswer.objects.create(video=video, question=question, student=user, request_id=values['request_id'],
        question_revision=question.revision, snapshot={'prompt': question.prompt, 'kind': question.kind, 'choices': question.choices,
            'hint': question.hint, 'start_time': question.start_time, 'multiple': question.multiple},
        selected_ids=selected, text=text, is_correct=correct, rewind_to=rewind)
    if correct is not False:
        progress.passed[str(question.pk)] = question.revision
        progress.replay_position = None
    elif rewind is not None:
        progress.position = rewind
        progress.replay_position = rewind
        progress.playback_credit = 0
    if pending_question(video, progress) is None and progress.watched_until >= video.duration - min(0.1, video.duration * 0.01) and progress.completed_at is None:
        progress.completed_at = timezone.now()
    progress.save(update_fields=['position', 'replay_position', 'completed_at', 'playback_credit', 'passed', 'updated_at'])
    return answer
