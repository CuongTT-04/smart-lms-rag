"""Bounded cross-worker admission and content-free operational signals."""
from contextlib import contextmanager
from datetime import timedelta
import json
import math
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlsplit
from urllib.request import Request

from django.db import transaction
from django.db.models import Count, Sum, Avg
from django.utils import timezone
from apps.documents.exceptions import DocumentError
from .models import GenerationGate, GenerationEvent
from .runtime import setting
from .rag.errors import VALIDATION_ERROR_CODES

SAFE_CODES = frozenset({'AI_QUOTA_EXCEEDED', 'AI_QUEUE_FULL', 'AI_QUEUE_TIMEOUT',
    'GENERATION_TIMEOUT', 'GENERATION_UNAVAILABLE', 'GENERATION_BUSY', 'GENERATION_CONFIG_MISMATCH',
    'INVALID_GENERATION', 'OUTPUT_LIMIT_REACHED', 'INCOMPLETE_GENERATION', 'OUT_OF_MEMORY',
    'SUMMARY_GENERATION_FAILED', 'SUMMARY_SOURCE_INCOMPLETE', 'SCOPE_CHANGED', 'NOT_FOUND',
    'AI_NOT_ALLOWED', 'INVALID_REQUEST'}) | VALIDATION_ERROR_CODES


def limits():
    values = {}
    for key, default, low, high in [('hourly_student', 20, 1, 10000), ('concurrent', 1, 1, 2),
                                  ('waiting', 5, 0, 100), ('queue_seconds', 10, 1, 10)]:
        try:
            value = int(setting('AI_' + key.upper(), default))
            if not low <= value <= high:
                raise ValueError(key)
            values[key] = value
        except (TypeError, ValueError) as exc:
            raise DocumentError('GENERATION_UNAVAILABLE', 'Cấu hình vận hành AI không hợp lệ.', 503) from exc
    return values


def _lock():
    GenerationGate.objects.get_or_create(pk=1)
    GenerationGate.objects.select_for_update().get(pk=1)


def _expire(now):
    for status, code in [('QUEUED', 'AI_QUEUE_TIMEOUT'), ('RUNNING', 'GENERATION_TIMEOUT')]:
        GenerationEvent.objects.filter(status=status, expires_at__lte=now).update(
            status='FAILED', code=code, finished_at=now)


def admit(user, mode):
    if mode not in ('qa', 'hint', 'summary'):
        raise ValueError('Unknown generation mode')
    policy = limits()
    error = None
    with transaction.atomic():
        _lock()
        now = timezone.now()
        _expire(now)
        hourly = GenerationEvent.objects.filter(user=user, created_at__gt=now-timedelta(hours=1)).exclude(status='REJECTED').count()
        running = GenerationEvent.objects.filter(status='RUNNING').count()
        waiting = GenerationEvent.objects.filter(status='QUEUED').count()
        if user.role == 'STUDENT' and hourly >= policy['hourly_student']:
            error = ('AI_QUOTA_EXCEEDED', 'Bạn đã hết hạn mức AI trong một giờ. Vui lòng thử lại sau.', 429)
        elif (running >= policy['concurrent'] or waiting > 0) and waiting >= policy['waiting']:
            error = ('AI_QUEUE_FULL', 'Hàng đợi AI đã đầy. Vui lòng thử lại sau.', 429)
        active = not error and running < policy['concurrent'] and waiting == 0
        event = GenerationEvent.objects.create(user=user, mode=mode,
            status='REJECTED' if error else 'RUNNING' if active else 'QUEUED',
            code=error[0] if error else '', finished_at=now if error else None,
            expires_at=now+timedelta(seconds=150 if active else policy['queue_seconds']))
    if error:
        raise DocumentError(*error)
    return event


def claim(event):
    with transaction.atomic():
        _lock()
        now = timezone.now()
        _expire(now)
        current = GenerationEvent.objects.get(pk=event.pk)
        if current.status == 'FAILED':
            raise DocumentError(current.code, 'Lượt AI đã hết thời gian xử lý. Vui lòng thử lại.',
                                429 if current.code == 'AI_QUEUE_TIMEOUT' else 503)
        if current.status == 'RUNNING':
            return True
        if current.status != 'QUEUED':
            raise DocumentError('GENERATION_UNAVAILABLE', 'Lượt AI không còn hiệu lực.', 503)
        first = GenerationEvent.objects.filter(status='QUEUED').order_by('created_at', 'id').first()
        if first.pk == event.pk and GenerationEvent.objects.filter(status='RUNNING').count() < limits()['concurrent']:
            GenerationEvent.objects.filter(pk=event.pk).update(status='RUNNING', expires_at=now+timedelta(seconds=150))
            return True
    return False


@contextmanager
def generation_slot(user, mode):
    event = admit(user, mode)
    started = monotonic()
    try:
        while not claim(event):
            if monotonic()-started >= limits()['queue_seconds']:
                raise DocumentError('AI_QUEUE_TIMEOUT', 'AI đang bận. Vui lòng thử lại sau.', 429)
            sleep(0.05)

        def call(generate, **arguments):
            if not GenerationEvent.objects.filter(pk=event.pk, status='RUNNING', gateway_calls=0,
                    expires_at__gt=timezone.now()).update(gateway_calls=1):
                raise DocumentError('GENERATION_TIMEOUT', 'Lượt AI đã hết hiệu lực.', 503)
            before = monotonic()
            try:
                output = generate(**arguments)
                usage = output.get('usage') if isinstance(output, dict) else None
                if mode == 'summary' and isinstance(output, dict):
                    usage = {'input_tokens': output.get('input_tokens')}
                tokens = {key: value for key, value in (usage if isinstance(usage, dict) else {}).items()
                          if key in ('input_tokens', 'output_tokens') and type(value) is int and 0 <= value <= 10000000}
                GenerationEvent.objects.filter(pk=event.pk).update(**tokens)
                return output
            finally:
                elapsed = (monotonic()-before)*1000
                if math.isfinite(elapsed):
                    GenerationEvent.objects.filter(pk=event.pk).update(duration_ms=max(0, elapsed))

        yield call
    except BaseException as exc:
        code = getattr(exc, 'code', '')
        GenerationEvent.objects.filter(pk=event.pk, status__in=['RUNNING', 'QUEUED']).update(
            status='FAILED', code=code if code in SAFE_CODES else 'GENERATION_UNAVAILABLE', finished_at=timezone.now())
        raise
    else:
        GenerationEvent.objects.filter(pk=event.pk, status='RUNNING').update(status='COMPLETED', finished_at=timezone.now())


def gateway_health():
    """No embedding/model load and no private URLs, config or exception text in output."""
    from .remote import NoRedirect, build_opener
    try:
        url = setting('AI_INFERENCE_URL').rstrip('/')
        parsed = urlsplit(url)
        token = setting('AI_INFERENCE_TOKEN')
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or len(token) < 32):
            raise ValueError('Invalid connection configuration')
        expected = json.loads(Path(setting('AI_GENERATION_CONFIG')).read_text(encoding='utf-8'))
        request = Request(url+'/health', headers={'Authorization':'Bearer '+token, 'ngrok-skip-browser-warning':'1'})
        with build_opener(NoRedirect()).open(request, timeout=3) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError('Oversized health')
        value = json.loads(raw)
        if value.get('config') != expected:
            return dict(status='UNAVAILABLE', code='GENERATION_CONFIG_MISMATCH')
        replicas, active = value.get('replicas'), value.get('in_flight')
        if type(value.get('ready')) is not bool or type(replicas) is not int or not 1 <= replicas <= 16 or type(active) is not int or not 0 <= active <= replicas:
            raise ValueError('Invalid health')
        return dict(status='READY' if value['ready'] else 'DRAINING', replicas=replicas, in_flight=active)
    except Exception:
        return dict(status='UNAVAILABLE', code='GENERATION_UNAVAILABLE')


def operations_snapshot():
    now = timezone.now()
    events = GenerationEvent.objects.filter(created_at__gte=now-timedelta(hours=24))
    with transaction.atomic():
        _lock()
        _expire(now)
    return dict(protocol='ayo_operations_v1', as_of=now.isoformat(), window_hours=24, limits=limits(),
        counting='One admitted generation step; polling, replay and no-source answers do not consume quota.',
        queue=dict(running=GenerationEvent.objects.filter(status='RUNNING').count(),
                   waiting=GenerationEvent.objects.filter(status='QUEUED').count()),
        outcomes={row['status']: row['total'] for row in events.values('status').annotate(total=Count('id'))},
        errors={row['code']: row['total'] for row in events.exclude(code='').values('code').annotate(total=Count('id'))},
        generation=events.aggregate(gateway_calls=Sum('gateway_calls'), mean_generation_ms=Avg('duration_ms'),
                                    input_tokens=Sum('input_tokens'), output_tokens=Sum('output_tokens')),
        gateway=gateway_health())
