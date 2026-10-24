"""Server-owned AI policy; never derive exam state or answer keys from client data."""
from django.db import transaction
from django.utils import timezone
from apps.courses.assessment_models import Assessment, AssessmentAttempt
from apps.courses.assessment_services import expire
from apps.documents.exceptions import DocumentError
from apps.documents.retrieval_scope import resolve_scope


def enforce_chat_policy(user, data):
    if not user.is_authenticated or not user.is_active:
        raise DocumentError('UNAUTHENTICATED', 'Vui lòng đăng nhập lại.', 401)
    now = timezone.now()
    if user.role == 'STUDENT':
        # Locks are held only for local lifecycle updates, never for an LLM call.
        with transaction.atomic():
            attempts = AssessmentAttempt.objects.select_for_update().select_related('assessment').filter(
                student=user, assessment__mode='TEST', status='DRAFT')
            blocked = False
            for attempt in attempts:
                expire(attempt)
                if attempt.status == 'DRAFT' and now < min(attempt.expires_at, attempt.assessment.due_at):
                    blocked = True
            if blocked:
                raise DocumentError('AI_NOT_ALLOWED', 'Không thể sử dụng AI trong khi làm bài kiểm tra.', 403)
    if data['mode'] != 'hint':
        return None
    assessment = Assessment.objects.select_related('session__classroom__course').filter(
        pk=data.get('assessment_id'), removed_at__isnull=True, is_published=True,
        session__classroom__course_id=data['course_id']).first()
    if not assessment:
        raise DocumentError('NOT_FOUND', 'Bài tập không khả dụng.', 404)
    if (data.get('session_id') and str(assessment.session_id) != str(data['session_id'])) or (
        data.get('classroom_id') and str(assessment.session.classroom_id) != str(data['classroom_id'])):
        raise DocumentError('NOT_FOUND', 'Bài tập không thuộc phạm vi đã chọn.', 404)
    resolve_scope(user, data['course_id'], session_id=assessment.session_id, mode='hint')
    if assessment.mode != 'PRACTICE':
        raise DocumentError('AI_NOT_ALLOWED', 'Chỉ hỗ trợ gợi ý cho bài ôn tập.', 403)
    question = None
    if assessment.kind == 'QUIZ':
        raw = next((q for q in assessment.questions if str(q['id']) == str(data.get('question_id'))), None)
        if raw is None:
            raise DocumentError('INVALID_REQUEST', 'Vui lòng chọn câu hỏi thuộc bài ôn tập.', 400)
        question = {'id': str(raw['id']), 'prompt': raw['prompt'], 'choices': [
            {'id': str(c['id']), 'text': c['text']} for c in raw.get('choices', [])]}
    elif data.get('question_id'):
        raise DocumentError('INVALID_REQUEST', 'Bài tự luận không nhận mã câu trắc nghiệm.', 400)
    return {'assessment_id': str(assessment.pk), 'title': assessment.title,
            'description': assessment.description, 'kind': assessment.kind, 'question': question}
