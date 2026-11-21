"""Server-owned reading steps based on public tasks and model-selected sources."""
import hashlib
import json

from apps.documents.exceptions import DocumentError
from apps.documents.retrieval_scope import resolve_scope
from .models import ChatResponseRecord
from .policy import enforce_chat_policy


def prepare_hint(user, data):
    exercise = enforce_chat_policy(user, data)
    selectors = {key: str(data.get(key) or '') for key in (
        'course_id', 'classroom_id', 'session_id', 'assessment_id', 'question_id')}
    selectors['document_ids'] = data.get('document_ids')
    scope = resolve_scope(user, data['course_id'], data.get('classroom_id'),
                          data.get('session_id'), data.get('document_ids'), 'hint')
    selectors['versions'] = list(scope.allowed_version_ids)
    fingerprint = hashlib.sha256(json.dumps(
        [selectors, exercise], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    step = 0
    history = []
    if data.get('previous_hint_id'):
        previous = ChatResponseRecord.objects.filter(
            pk=data['previous_hint_id'], user=user).first()
        if not previous or not previous.hint_state:
            raise DocumentError('NOT_FOUND', 'Lượt gợi ý không khả dụng.', 404)
        if previous.hint_state['fingerprint'] != fingerprint:
            raise DocumentError('SCOPE_CHANGED', 'Bài hoặc câu hỏi đã thay đổi. Hãy mở lại gợi ý.', 409)
        step = previous.hint_state['step']
        history = previous.hint_state.get('history', [])[-3:]
    if data.get('hint_action') == 'next_step':
        step = min(step + 1, 2)
    return exercise, dict(fingerprint=fingerprint, step=step, history=history)


def apply_hint(result, exercise, state, action, question):
    if result['status'] != 'ANSWERED' or not result['citations']:
        return None
    result['hint'] = dict(step=state['step'], action=action, can_advance=state['step'] < 2)
    # Each immutable result is a branch point. Concurrent retries cannot skip steps.
    return {**state, 'history': (state['history'] + [dict(user=question, assistant=result['answer'])])[-3:]}
