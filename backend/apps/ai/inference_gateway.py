"""Small authenticated notebook gateway. Authorization/retrieval stay in Django.

Standard library only at import time so this module can be embedded in a cell.
Never expose without TLS (the notebook uses an ngrok HTTPS tunnel).
"""
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from time import monotonic


def public_exercise(value):
    if value is None:
        return None
    from apps.ai.rag import ExerciseContext
    if not isinstance(value, dict) or set(value) - {'assessment_id', 'title', 'description', 'kind', 'question'}:
        raise ValueError('Only visible exercise fields are allowed')
    question = value.get('question')
    if value.get('kind') == 'QUIZ':
        if not isinstance(question, dict) or set(question) - {'id', 'prompt', 'choices'}:
            raise ValueError('Invalid visible question')
        choices = question.get('choices', [])
        if not isinstance(choices, list) or any(not isinstance(c, dict) or set(c) != {'id', 'text'} for c in choices):
            raise ValueError('Invalid visible choices')
        return ExerciseContext(exercise_id=f"{value['assessment_id']}:{question['id']}",
            question=question['prompt'], choices=tuple(c['text'] for c in choices))
    if value.get('kind') != 'TEXT' or question is not None:
        raise ValueError('Invalid exercise')
    return ExerciseContext(exercise_id=value['assessment_id'],
        question='\n'.join(p for p in (value.get('title'), value.get('description')) if p))


def start_gateway(pipeline, token, public_config, *, port=8765):
    if not isinstance(token, str) or len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError('Use a random ASCII token of at least 32 characters')
    pipelines = tuple(pipeline) if isinstance(pipeline, (list, tuple)) else (pipeline,)
    if not pipelines or len({id(item) for item in pipelines}) != len(pipelines) or any(
            not callable(getattr(item, 'generate_answer', None)) for item in pipelines):
        raise ValueError('Provide distinct initialized pipelines')
    locks = [Lock() for _ in pipelines]
    guard = Lock()
    cursor = 0
    draining = False

    def acquire():
        nonlocal cursor
        with guard:
            if not draining:
                for offset in range(len(pipelines)):
                    index = (cursor + offset) % len(pipelines)
                    if locks[index].acquire(blocking=False):
                        cursor = (index + 1) % len(pipelines)
                        return index
        return None

    def busy_count():
        return sum(lock.locked() for lock in locks)

    def wait_idle(timeout=110):
        nonlocal draining
        with guard:
            draining = True
        deadline = monotonic() + timeout
        acquired = []
        try:
            for lock in locks:
                if not lock.acquire(timeout=max(0, deadline - monotonic())):
                    return False
                acquired.append(lock)
            return True
        finally:
            for lock in acquired:
                lock.release()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(100)

        def log_message(self, *args):
            pass  # No tokens, prompts, paths or answers in HTTP access logs.

        def reply(self, status, data):
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def authorized(self):
            provided = self.headers.get('Authorization', '').encode('utf-8')
            if not hmac.compare_digest(provided, ('Bearer ' + token).encode('ascii')):
                self.reply(401, {'code': 'UNAUTHORIZED'})
                return False
            return True

        def do_GET(self):
            if self.authorized():
                if self.path == '/health':
                    count = busy_count()
                    self.reply(200, {'ready': not draining, 'busy': count == len(pipelines),
                        'replicas': len(pipelines), 'in_flight': count, 'config': public_config})
                else:
                    self.reply(404, {'code': 'NOT_FOUND'})

        def do_POST(self):
            if not self.authorized():
                return
            if self.path != '/generate':
                return self.reply(404, {'code': 'NOT_FOUND'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if self.headers.get('Transfer-Encoding') or not 0 < length <= 1024 * 1024:
                    return self.reply(413, {'code': 'REQUEST_TOO_LARGE'})
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or set(data) != {'question', 'mode', 'contexts', 'exercise', 'config'}:
                    raise ValueError('Invalid fields')
                if data['config'] != public_config:
                    return self.reply(409, {'code': 'CONFIG_MISMATCH'})
                if (not isinstance(data['question'], str) or not 0 < len(data['question']) <= 8000
                        or data['mode'] not in ('qa', 'hint') or not isinstance(data['contexts'], list)
                        or len(data['contexts']) > 100):
                    raise ValueError('Invalid request')
                exercise = public_exercise(data['exercise'])
            except (ValueError, TypeError, KeyError, UnicodeError):
                return self.reply(400, {'code': 'INVALID_REQUEST'})
            index = acquire()
            if index is None:
                return self.reply(429, {'code': 'GENERATION_BUSY'})
            try:
                result = pipelines[index].generate_answer(question=data['question'], mode=data['mode'],
                    contexts=data['contexts'], exercise=exercise)
                used = list(result.trace.used_source_ids)
                output = result.to_dict()
                if any(ref['source_id'] not in used for ref in output['references']):
                    return self.reply(503, {'code': 'INVALID_GENERATION'})
                self.reply(200, {'output': output, 'used_source_ids': used})
            except Exception as exc:
                code = getattr(exc, 'code', 'GENERATION_UNAVAILABLE')
                safe = code if code in {'INVALID_REQUEST', 'INVALID_GENERATION', 'GENERATION_TIMEOUT',
                    'OUTPUT_LIMIT_REACHED', 'INCOMPLETE_GENERATION', 'OUT_OF_MEMORY'} else 'GENERATION_UNAVAILABLE'
                self.reply(400 if safe == 'INVALID_REQUEST' else 503, {'code': safe})
            finally:
                locks[index].release()

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.wait_idle = wait_idle
    server.busy_count = busy_count
    server.service_thread = Thread(target=server.serve_forever, daemon=True)
    server.service_thread.start()
    return server
