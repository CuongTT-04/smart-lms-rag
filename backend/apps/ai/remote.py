"""Authenticated HTTPS transport for the existing W4 generator boundary."""
import json
import os
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from apps.documents.exceptions import DocumentError
from .rag.errors import public_validation_error


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def generate_answer(*, question, mode, contexts, exercise, config, history=None):
    try:
        url = os.environ['AI_INFERENCE_URL'].rstrip('/')
        parsed = urlsplit(url)
        token = os.environ['AI_INFERENCE_TOKEN']
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in ('', '/') or len(token) < 32):
            raise ValueError('Invalid remote configuration')
        payload = dict(question=question, mode=mode, contexts=contexts, exercise=exercise, config=config)
        if history is not None:
            payload.update(history=history, history_protocol='chat_history_v1')
        body = json.dumps(payload).encode('utf-8')
        request = Request(url + '/generate', data=body, headers={
            'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': '1'})
        with build_opener(NoRedirect()).open(request, timeout=min(config['timeout_seconds'] + 15, 100)) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Oversized response')
        result = json.loads(raw)
        expected = {'output', 'used_source_ids'} | ({'memory'} if history is not None else set())
        if not isinstance(result, dict) or set(result) != expected:
            if history is not None:
                raise DocumentError('GENERATION_CONFIG_MISMATCH', 'Gateway chưa hỗ trợ context nhiều lượt. Cần chạy cell mới.', 503)
            raise ValueError('Invalid envelope')
        output, used = result['output'], result['used_source_ids']
        allowed = {context['source_id'] for context in contexts}
        if not isinstance(used, list) or not all(isinstance(item, str) and item in allowed for item in used):
            raise ValueError('Invalid prompt sources')
        if not isinstance(output, dict) or any(ref['source_id'] not in used for ref in output['references']):
            raise ValueError('Reference outside prompt')
        if history is not None:
            memory = result['memory']
            if (not isinstance(memory, dict) or set(memory) != {'protocol','turns_used','turns_dropped','history_tokens'}
                or memory['protocol'] != 'chat_history_v1' or any(type(memory[k]) is not int or memory[k]<0 for k in ('turns_used','turns_dropped','history_tokens'))
                or memory['turns_used']>4 or memory['history_tokens']>768 or memory['turns_used']+memory['turns_dropped']!=len(history)):
                raise ValueError('Invalid memory acknowledgment')
            return {**output, '_memory': memory}
        return output  # Existing services.map_output validates the complete public result.
    except DocumentError:
        raise
    except HTTPError as exc:
        try:
            failure = json.loads(exc.read(4096))
            remote = failure.get('code')
        except Exception:
            remote, failure = None, {}
        if not isinstance(remote, str):
            remote = None
        if exc.code == 503 and remote == 'INVALID_GENERATION':
            raise DocumentError(*public_validation_error(failure.get('reason'))) from exc
        errors = {
            (503, 'OUTPUT_LIMIT_REACHED'): ('OUTPUT_LIMIT_REACHED', 'Câu trả lời vượt giới hạn độ dài. Hãy thử câu hỏi cụ thể hơn.', 503),
            (503, 'INCOMPLETE_GENERATION'): ('INCOMPLETE_GENERATION', 'Mô hình chưa hoàn tất câu trả lời. Vui lòng thử lại.', 503),
            (503, 'GENERATION_TIMEOUT'): ('GENERATION_TIMEOUT', 'Mô hình xử lý quá lâu. Vui lòng thử lại.', 503),
            (503, 'OUT_OF_MEMORY'): ('OUT_OF_MEMORY', 'Dịch vụ AI thiếu bộ nhớ xử lý. Vui lòng thử lại sau.', 503),
            (429, 'GENERATION_BUSY'): ('GENERATION_BUSY', 'AI đang xử lý các yêu cầu khác. Vui lòng thử lại sau.', 429),
            (409, 'CONFIG_MISMATCH'): ('GENERATION_CONFIG_MISMATCH', 'Cấu hình backend và Kaggle chưa khớp.', 503),
        }
        if (exc.code, remote) in errors:
            raise DocumentError(*errors[(exc.code, remote)]) from exc
        if exc.code == 400:
            if history is not None:
                raise DocumentError('GENERATION_CONFIG_MISMATCH', 'Gateway chưa hỗ trợ context nhiều lượt hoặc cấu hình chưa khớp.', 503) from exc
            raise DocumentError('INVALID_REQUEST', 'Yêu cầu không phù hợp với chính sách trợ lý.', 400) from exc
        raise DocumentError('GENERATION_UNAVAILABLE', 'Dịch vụ AI chưa sẵn sàng. Vui lòng thử lại.', 503) from exc
    except Exception as exc:
        raise DocumentError('GENERATION_UNAVAILABLE', 'Không kết nối được dịch vụ AI.', 503) from exc
