"""Owner-scoped source summaries; bounded inference steps and legacy task compatibility."""
from copy import deepcopy
from datetime import timedelta
import re
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from apps.documents.exceptions import DocumentError
from apps.documents.models import DocumentVersion
from apps.documents.retrieval_adapter import live_scope, assert_scope_and_citations_live
from apps.documents.retrieval_contracts import Chunk
from apps.documents.retrieval_scope import resolve_scope
from .models import ChatResponseRecord, SummaryTask
from .policy import enforce_chat_policy
from .rag.summary import PROTOCOL, VALIDATION_REASONS, validate_paragraphs
from .rag.guardrails import check_output_policy
from .remote import summarize_step
from .runtime import get_runtime

MAX_PAGES, MAX_CHUNKS, MAX_CHARACTERS = 20, 300, 600000
MAP_BATCH_BLOCKS = 8
REDUCE_BATCH_NOTES = 2
COMPACT_FINAL_CHARACTERS = 4000
SOURCE_SECTIONS = 'source_sections_v1'


def compact_note_blocks(notes):
    """Re-read every character of the final notes with the shorter map output budget."""
    blocks = []
    for note in notes:
        for paragraph in note['paragraphs']:
            text = paragraph['text']
            for offset in range(0, len(text), 700):
                blocks.append(dict(id=f'B{len(blocks)+1}', source_id=paragraph['sources'][0], text=text[offset:offset+700]))
    return blocks


def separate_source_footers(paragraphs):
    """Separate only a trailing, redundant source-ID list; never rewrite summary prose."""
    normalized, adjustments = deepcopy(paragraphs), []
    for index, paragraph in enumerate(normalized):
        match = re.search(r'\s*Các nguồn tham khảo:\s*(S\.[1-9]\d*(?:,\s*S\.[1-9]\d*)*)\.\s*$', paragraph['text'])
        if match is None:
            continue
        ids = {'S' + value for value in re.findall(r'S\.([1-9]\d*)', match.group(1))}
        text = paragraph['text'][:match.start()].strip()
        if not ids.issubset(set(paragraph['sources'])) or not text:
            raise DocumentError('SUMMARY_GENERATION_FAILED', 'Danh sách nguồn trong lời văn không hợp lệ.', 503)
        adjustments.append(dict(paragraph=index, removed_footer=match.group().strip()))
        paragraph['text'] = text
    return normalized, adjustments


def task_scope(user, selector):
    user.refresh_from_db()
    enforce_chat_policy(user, {**selector, 'question': 'Tóm tắt học liệu', 'mode': 'qa'})
    scope = resolve_scope(user, selector['course_id'], selector.get('classroom_id'),
        selector.get('session_id'), selector['document_ids'], 'qa')
    if scope.document_ids and len(scope.allowed_version_ids) != len(scope.document_ids):
        raise DocumentError('NOT_FOUND', 'Học liệu không khả dụng hoặc bạn không có quyền truy cập.', 404)
    return scope


def owned_task(user, task_id):
    task = SummaryTask.objects.filter(pk=task_id, user=user).select_related('version').first()
    if task is None:
        raise DocumentError('NOT_FOUND', 'Tiến trình không khả dụng.', 404)
    scope = task_scope(user, task.selector)
    if scope.allowed_version_ids != (str(task.version_id),) or task.version.checksum_sha256 != task.state['checksum']:
        raise DocumentError('SCOPE_CHANGED', 'Học liệu hoặc quyền đã thay đổi.', 409)
    sources = task.state.get('sources', (task.result or {}).get('citations', []))
    assert_scope_and_citations_live(user, scope, citations=sources)
    return task


def descriptor(task):
    state = task.state
    result = task.result if task.status == 'COMPLETED' else None
    if result and result.get('coverage', {}).get('citation_scope') != 'input_range':
        # Older summaries keep their raw result; only the source presentation changes.
        result = {**render_result(task, state), 'timing': result['timing']}
    return dict(id=str(task.pk), mode='summary', status=task.status,
        progress=dict(phase='map' if state['cursor'] < len(state['blocks']) else 'reduce',
            blocks_read=state['cursor'], blocks_total=len(state['blocks']), steps=state['steps']),
        result=result,
        error=dict(code=task.error_code, **state.get('failure_details', {})) if task.status == 'FAILED' else None)


def answer_summary(*, user, data, request_id, runtime=None):
    selector = {key: str(data[key]) for key in ('course_id', 'classroom_id', 'session_id') if data.get(key)}
    selector['document_ids'] = data.get('document_ids', [])
    scope = task_scope(user, selector)
    if len(scope.allowed_version_ids) != 1:
        raise DocumentError('SUMMARY_SCOPE_INVALID', 'Chọn đúng một học liệu.', 400)
    version = DocumentVersion.objects.get(pk=scope.allowed_version_ids[0])
    start, end = data.get('page_start', 1), data.get('page_end', version.page_count)
    if start > end or end > version.page_count or end - start + 1 > MAX_PAGES:
        raise DocumentError('SUMMARY_SCOPE_INVALID', 'Chọn tối đa 20 trang PDF hợp lệ.', 400)
    client_id = data.get('summary_request_id') or request_id
    previous = SummaryTask.objects.filter(user=user, client_request_id=client_id).first()
    if previous:
        if previous.selector != selector or previous.state['start'] != start or previous.state['end'] != end:
            raise DocumentError('MESSAGE_CONFLICT', 'Mã tóm tắt đã được dùng cho phạm vi khác.', 409)
        return descriptor(owned_task(user, previous.pk))
    runtime = runtime or get_runtime()
    chunks = []
    for catalog_id, chunk in runtime.catalog.items():
        if not isinstance(chunk, Chunk) or chunk.version_id != str(version.pk):
            continue
        if (chunk.chunk_id != catalog_id or chunk.document_id != str(version.document_id) or chunk.course_id != scope.course_id
                or chunk.source_checksum != version.checksum_sha256
                or not 1 <= chunk.page_number <= version.page_count):
            raise DocumentError('INVALID_RETRIEVAL', 'Nguồn lập chỉ mục không khớp.', 503)
        if start <= chunk.page_number <= end:
            chunks.append(chunk)
    if len(chunks) > MAX_CHUNKS or sum(len(chunk.text) for chunk in chunks) > MAX_CHARACTERS:
        raise DocumentError('SUMMARY_SCOPE_INVALID', 'Phạm vi quá dài. Chọn ít trang hơn.', 400)
    chunks.sort(key=lambda chunk: (chunk.page_number, chunk.chunk_order, chunk.chunk_id))
    if {chunk.page_number for chunk in chunks if chunk.text.strip()} != set(range(start, end + 1)):
        raise DocumentError('SUMMARY_SOURCE_INCOMPLETE', 'Một số trang chưa có văn bản trong chỉ mục.', 503)
    sources, blocks = [], []
    for index, chunk in enumerate(chunks, 1):
        source_id = f'S{index}'
        sources.append(dict(source_id=source_id, chunk_id=chunk.chunk_id, excerpt=chunk.text,
            document_id=chunk.document_id, version_id=chunk.version_id, document_title=chunk.document_title,
            page_number=chunk.page_number, section_title=chunk.section_title))
        offset = 0
        while offset < len(chunk.text):
            stop = min(offset + 700, len(chunk.text))
            if stop < len(chunk.text):
                boundary = chunk.text.rfind(' ', offset + 350, stop)
                if boundary > offset:
                    stop = boundary + 1
            blocks.append(dict(id=f'B{len(blocks)+1}', source_id=source_id, text=chunk.text[offset:stop]))
            offset = stop
    live_scope(user, scope)
    state = dict(checksum=version.checksum_sha256, start=start, end=end, pages=version.page_count,
        synthesis_strategy=SOURCE_SECTIONS,
        sources=sources, blocks=blocks, cursor=0, notes=[], next_notes=[], steps=0, config=deepcopy(runtime.config))
    with transaction.atomic():
        task, created = SummaryTask.objects.get_or_create(user=user, client_request_id=client_id,
            defaults=dict(document_id=version.document_id, version=version, selector=selector, state=state))
        if not created and (task.selector != selector or task.state['start'] != start or task.state['end'] != end):
            raise DocumentError('MESSAGE_CONFLICT', 'Mã tóm tắt đã được dùng.', 409)
    return descriptor(owned_task(user, task.pk))


def render_result(task, state):
    paragraphs = state['notes'][0]['paragraphs'] if state['notes'] else []
    if not paragraphs:
        raise DocumentError('SUMMARY_SOURCE_INCOMPLETE', 'Không đủ nội dung học để tổng hợp.', 503)
    citations = [dict(label=index, **{k: v for k, v in source.items() if k != 'source_id'})
        for index, source in enumerate(state['sources'], 1)]
    lines = [paragraph['text'].strip() for paragraph in paragraphs]
    return dict(request_id=str(task.pk), mode='summary', status='ANSWERED', answer='\n\n'.join(lines),
        citations=citations, timing=dict(total_ms=round((timezone.now()-task.created_at).total_seconds()*1000, 3)),
        coverage=dict(method=PROTOCOL, citation_scope='input_range', document_id=str(task.document_id), version_id=str(task.version_id),
            source_sha256=state['checksum'], page_start=state['start'], page_end=state['end'],
            document_pages=state['pages'], pages_scanned=list(range(state['start'], state['end']+1)),
            chunks_scanned=len(state['sources']), blocks_read=state['cursor'], blocks_total=len(state['blocks']),
            generation_steps=state['steps'], whole_document=state['start'] == 1 and state['end'] == state['pages'],
            **({'final_synthesis': state['final_synthesis']} if 'final_synthesis' in state else {}),
            **({'resumed_from_saved_notes': True, 'reused_generation_steps': state['recovery']['reused_steps']}
               if 'recovery' in state else {}),
            **({'format_retries': sum(row['attempts'] for row in state['source_retries'].values()),
                'generation_attempts': state['steps']+sum(row['attempts'] for row in state['source_retries'].values())}
               if state.get('source_retries') else {})))


def advance_summary(user, task_id, runtime=None):
    task = owned_task(user, task_id)
    with transaction.atomic():
        task = SummaryTask.objects.select_for_update().get(pk=task.pk)
        if task.status in ('COMPLETED', 'FAILED'):
            return descriptor(task)
        if task.status == 'PROCESSING' and task.lease_expires_at > timezone.now():
            return descriptor(task)
        if timezone.now()-task.created_at > timedelta(minutes=30) or task.state['steps'] >= 100:
            task.status, task.error_code = 'FAILED', 'SUMMARY_EXPIRED'
            task.save(update_fields=['status', 'error_code', 'updated_at'])
            return descriptor(task)
        lease = uuid4()
        task.status, task.lease_token, task.lease_expires_at = 'PROCESSING', lease, timezone.now()+timedelta(seconds=120)
        task.save(update_fields=['status', 'lease_token', 'lease_expires_at', 'updated_at'])
    state = deepcopy(task.state)
    try:
        phase = 'map' if state['cursor'] < len(state['blocks']) else 'reduce'
        source_sections = state.get('synthesis_strategy') == SOURCE_SECTIONS
        if source_sections and phase != 'map':
            raise DocumentError('SUMMARY_GENERATION_FAILED', 'Tiến trình nguồn không hợp lệ.', 503)
        if phase == 'reduce' and len(state['notes']) == 1 and state['next_notes']:
            state['next_notes'].append(state['notes'].pop())
            state['notes'], state['next_notes'] = state['next_notes'], []
        retry = state.get('source_retries', {}).get(str(state['cursor']), {})
        batch_size = min(MAP_BATCH_BLOCKS, retry.get('batch_blocks', MAP_BATCH_BLOCKS))
        records = state['blocks'][state['cursor']:state['cursor']+batch_size] if phase == 'map' else state['notes'][:REDUCE_BATCH_NOTES]
        compact_final = (phase == 'reduce' and (bool(state.get('final_sections')) or (
            2 <= len(state['notes']) <= 3 and not state['next_notes']
            and sum(len(p['text']) for note in state['notes'] for p in note['paragraphs']) > COMPACT_FINAL_CHARACTERS)))
        generation_phase = 'map' if compact_final else phase
        section_index = len(state.get('final_sections', []))
        generation_records = compact_note_blocks([state['notes'][section_index]]) if compact_final else records
        if compact_final and len(generation_records) > 32:
            raise DocumentError('SUMMARY_GENERATION_FAILED', 'Ghi chú cuối vượt phạm vi tổng hợp ngắn.', 503)
        runtime = runtime or get_runtime()
        if runtime.config != state['config']:
            raise DocumentError('GENERATION_CONFIG_MISMATCH', 'Cấu hình đã đổi giữa tiến trình tóm tắt. Vui lòng tạo lại.', 503)
        generate = getattr(runtime, 'summarize', summarize_step)
        owned_task(user, task.pk)
        from .operations import generation_slot
        with generation_slot(user, 'summary') as admitted:
            owned_task(user, task.pk)
            output = admitted(generate, phase=generation_phase, records=generation_records, config=runtime.config)
        if (not isinstance(output, dict) or set(output) != {'protocol', 'phase', 'consumed', 'input_tokens', 'paragraphs'}
                or output['protocol'] != PROTOCOL or output['phase'] != generation_phase
                or type(output['consumed']) is not int or not (1 if generation_phase == 'map' else 2) <= output['consumed'] <= len(generation_records)
                or type(output['input_tokens']) is not int or not 0 < output['input_tokens'] <= runtime.config['max_input_tokens']):
            raise DocumentError('SUMMARY_GENERATION_FAILED', 'Phản hồi tóm tắt không hợp lệ.', 503)
        if compact_final and output['consumed'] != len(generation_records):
            raise DocumentError('SUMMARY_GENERATION_FAILED', 'Bước tổng hợp cuối chưa đọc đủ ghi chú.', 503)
        consumed = output['consumed']
        allowed = {r['source_id'] for r in generation_records[:consumed]} if generation_phase == 'map' else {
            s for note in records[:consumed] for p in note['paragraphs'] for s in p['sources']}
        validate_paragraphs(output['paragraphs'], allowed, require_complete=source_sections)
        check_output_policy('\n'.join(p['text'] for p in output['paragraphs']),
                            [source['excerpt'] for source in state['sources']])
        paragraphs, adjustments = separate_source_footers(output['paragraphs'])
        if adjustments:
            state.setdefault('formatting_adjustments', []).append(dict(step=state['steps']+1, changes=adjustments))
        note = dict(paragraphs=paragraphs)
        if compact_final:
            if not note['paragraphs']:
                raise DocumentError('SUMMARY_GENERATION_FAILED', 'Một nhóm chủ đề chưa được tổng hợp.', 503)
            state.setdefault('final_sections', []).append(note)
            synthesis = state.setdefault('final_synthesis', dict(strategy='topic_sections', sections_total=len(state['notes']),
                sections_completed=0, input_blocks=0, input_characters=0,
                output_budget_tokens=640, source_association='representative_note_source_not_entailment')
            )
            synthesis['sections_completed'] += 1
            synthesis['input_blocks'] += len(generation_records)
            synthesis['input_characters'] += sum(len(row['text']) for row in generation_records)
            if len(state['final_sections']) == len(state['notes']):
                state['notes'] = [dict(paragraphs=[p for section in state.pop('final_sections') for p in section['paragraphs']])]
        elif phase == 'map':
            state['cursor'] += consumed
            if note['paragraphs']:
                state['notes'].append(note)
            if source_sections and state['cursor'] == len(state['blocks']):
                # Preserve source-grounded paragraphs instead of asking the model to rewrite its own claims.
                state['source_sections'] = deepcopy(state['notes'])
                state['final_synthesis'] = dict(strategy=SOURCE_SECTIONS, sections_total=len(state['notes']),
                    sections_completed=len(state['notes']), input_blocks=state['cursor'],
                    input_characters=sum(len(row['text']) for row in state['blocks']),
                    output_budget_tokens=640, generated_notes_rewritten=False)
                if state['notes']:
                    state['notes'] = [dict(paragraphs=[p for section in state['notes'] for p in section['paragraphs']])]
        else:
            if not note['paragraphs']:
                raise DocumentError('SUMMARY_GENERATION_FAILED', 'Bản tổng hợp rỗng.', 503)
            state['notes'] = state['notes'][consumed:]
            state['next_notes'].append(note)
            if not state['notes']:
                state['notes'], state['next_notes'] = state['next_notes'], []
        state['steps'] += 1
        state.pop('failure_details', None)
        completed = state['cursor'] == len(state['blocks']) and len(state['notes']) == 1 and not state['next_notes']
        owned_task(user, task.pk)
        with transaction.atomic():
            current = SummaryTask.objects.select_for_update().get(pk=task.pk)
            if current.lease_token != lease or current.lease_expires_at <= timezone.now():
                raise DocumentError('CHAT_SUPERSEDED', 'Bước tóm tắt đã hết hiệu lực.', 409)
            owned_task(user, task.pk)
            current.state, current.status = state, 'COMPLETED' if completed else 'PENDING'
            current.error_code = ''
            current.lease_token, current.lease_expires_at = None, None
            if completed:
                current.result = render_result(current, state)
                ChatResponseRecord.objects.get_or_create(id=current.pk, defaults=dict(user=user))
            elif state['cursor'] == len(state['blocks']) and not state['notes']:
                current.status, current.error_code = 'FAILED', 'SUMMARY_SOURCE_INCOMPLETE'
            current.save()
        return descriptor(owned_task(user, current.pk))
    except Exception as error:
        code = getattr(error, 'code', 'SUMMARY_GENERATION_FAILED')
        safe = code if code in ('GENERATION_BUSY', 'GENERATION_CONFIG_MISMATCH', 'GENERATION_UNAVAILABLE',
            'SUMMARY_SOURCE_INCOMPLETE', 'SCOPE_CHANGED', 'CHAT_SUPERSEDED',
            'AI_QUOTA_EXCEEDED', 'AI_QUEUE_FULL', 'AI_QUEUE_TIMEOUT', 'GENERATION_TIMEOUT') else 'SUMMARY_GENERATION_FAILED'
        details = {}
        remote_code = getattr(error, 'remote_code', None)
        if remote_code in {'INVALID_REQUEST', 'INVALID_GENERATION', 'GENERATION_TIMEOUT',
                           'OUTPUT_LIMIT_REACHED', 'INCOMPLETE_GENERATION', 'OUT_OF_MEMORY', 'GENERATION_UNAVAILABLE'}:
            details['remote_code'] = remote_code
        reason = getattr(error, 'validation_reason', None)
        if isinstance(reason, str) and reason in VALIDATION_REASONS:
            details['reason'] = reason
        if (task.state.get('synthesis_strategy') == SOURCE_SECTIONS and reason == 'SUMMARY_INCOMPLETE_SENTENCE'
                and task.state['cursor'] < len(task.state['blocks'])):
            retries = deepcopy(task.state.get('source_retries', {}))
            key = str(task.state['cursor'])
            if retries.get(key, {}).get('attempts', 0) < 1:
                retries[key] = dict(attempts=1, batch_blocks=max(1, MAP_BATCH_BLOCKS//2), reason=reason)
                SummaryTask.objects.filter(pk=task.pk, lease_token=lease).update(status='PENDING',error_code='',
                    lease_token=None,lease_expires_at=None,state={**task.state,'source_retries':retries})
                return descriptor(owned_task(user,task.pk))
        SummaryTask.objects.filter(pk=task.pk, lease_token=lease).update(
            status='PENDING' if safe in ('GENERATION_BUSY', 'AI_QUOTA_EXCEEDED', 'AI_QUEUE_FULL', 'AI_QUEUE_TIMEOUT') else 'FAILED', error_code=safe,
            lease_token=None, lease_expires_at=None, state={**task.state, 'failure_details': details})
        if safe in ('SCOPE_CHANGED', 'AI_QUOTA_EXCEEDED', 'AI_QUEUE_FULL', 'AI_QUEUE_TIMEOUT'):
            raise error
        return descriptor(owned_task(user, task.pk))
