"""Server-owned reading steps based on public tasks and model-selected sources."""
import hashlib
import json
import re

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
    if data.get('previous_hint_id'):
        previous = ChatResponseRecord.objects.filter(
            pk=data['previous_hint_id'], user=user).first()
        if not previous or not previous.hint_state:
            raise DocumentError('NOT_FOUND', 'Lượt gợi ý không khả dụng.', 404)
        if previous.hint_state['fingerprint'] != fingerprint:
            raise DocumentError('SCOPE_CHANGED', 'Bài hoặc câu hỏi đã thay đổi. Hãy mở lại gợi ý.', 409)
        step = previous.hint_state['step']
    if data.get('hint_action') == 'next_step':
        step = min(step + 1, 2)
    return exercise, dict(fingerprint=fingerprint, step=step)


def apply_hint(result, exercise, state, action):
    if result['status'] != 'ANSWERED' or not result['citations']:
        return None
    source = result['citations'][0]
    reference = f"[{source['label']}]"
    location = f"trang {source['page_number']} của học liệu “{source['document_title']}”"
    prompt = (exercise.get('question') or {}).get('prompt') or exercise['description'] or exercise['title']
    prompt = re.sub(r'\[(\d+)\]', r'(\1)', prompt)
    if action == 'explain_task':
        answer = (f"Yêu cầu đang làm là “{prompt}”.\n\n"
                  'Hãy tách đề thành các ý cần trả lời, chú ý đối tượng được hỏi và các từ như '
                  '“chức năng”, “bao nhiêu”, “vì sao” hoặc “so sánh” xuất hiện trong đề. '
                  f"Với mỗi ý, tìm thông tin hỗ trợ ở {location} {reference}.")
        if exercise['kind'] == 'QUIZ':
            answer += ' Đối chiếu từng lựa chọn với thông tin đó trước khi tự chọn đáp án.'
    elif action == 'practice':
        answer = (f"Hãy đối chiếu bản nháp vừa viết với yêu cầu “{prompt}”.\n\n"
                  f"Đánh dấu câu trong bản nháp có thông tin hỗ trợ ở {location} {reference}. "
                  'Tự kiểm tra xem còn ý nào của đề chưa được trả lời và bổ sung ý đó.')
    elif state['step'] == 1:
        answer = (f"Với yêu cầu “{prompt}”, hãy lập bảng hai cột “Ý đề hỏi” và “Thông tin tìm được”. "
                  f"Đọc {location}, ghi lại thông tin cho từng ý bằng lời của bạn {reference}. "
                  'Để trống phần chưa tìm thấy căn cứ và đọc tiếp phần liên quan trước khi kết luận.')
    elif state['step'] == 2:
        answer = (f"Dùng các ghi chú vừa lập để viết thử câu trả lời cho “{prompt}”. "
                  f"Mỗi ý cần đối chiếu được với {location} {reference}. "
                  'Chọn “Thử trả lời” để nhập bản nháp, rồi tự rà lại từng yêu cầu của đề.')
    else:
        answer = (f"Bắt đầu ở {location} {reference}. "
                  f"Đọc yêu cầu “{prompt}” và xác định đoạn nào giúp trả lời từng ý. "
                  'Khi đã đọc xong, chọn “Gợi ý bước tiếp theo” để lập ghi chú.')
    result['answer'] = answer
    result['citations'] = result['citations'][:1]
    result['hint'] = dict(step=state['step'], action=action, can_advance=state['step'] < 2)
    # Each immutable result is a branch point. Concurrent retries cannot skip steps.
    return state
