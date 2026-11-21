"""Explicit live acceptance on the existing philosophy PDF; no uploads or seeded LMS data."""
import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_gateway(config):
    request = Request(os.environ['AI_INFERENCE_URL'].rstrip('/') + '/health', headers={
        'Authorization': 'Bearer ' + os.environ['AI_INFERENCE_TOKEN'], 'ngrok-skip-browser-warning': '1'})
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            health = json.loads(response.read(65536))
        return dict(ready=bool(health.get('ready') and health.get('config') == config
                    and 'chat_history_v1' in health.get('capabilities', [])), http_status=200,
                    summary_ready=all(capability in health.get('capabilities', []) for capability in
                        ('coherent_summary_v1', 'summary_topic_paragraphs_v1', 'summary_validation_details_v1', 'summary_text_grammar_v1', 'summary_json_quotes_v1')))
    except HTTPError as error:
        return dict(ready=False, http_status=error.code, ngrok_offline=b'ERR_NGROK_3200' in error.read(65536))
    except Exception as error:
        return dict(ready=False, error=type(error).__name__)


def request_json(path, token, data=None):
    request = Request('http://127.0.0.1:8000' + path, data=None if data is None else json.dumps(data).encode(), headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
    try:
        with urlopen(request, timeout=150) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.loads(error.read())


def check_followups(scope, document, token, runtime, gateway):
    if not gateway['ready']:
        raise RuntimeError('Gateway is not ready; do not record follow-up acceptance.')
    from apps.ai.followups import CLARIFY
    status, conversation = request_json('/api/ai/conversations/', token, {**scope, 'document_id': str(document.pk)})
    assert status == 201
    conversation_id = conversation['id']
    selector = {**scope, 'document_ids': [str(document.pk)], 'conversation_id': conversation_id, 'mode': 'qa'}
    status, first = request_json('/api/ai/chat/', token, {**selector, 'question': 'Theo giáo trình, triết học là gì?',
        'client_message_id': str(uuid.uuid4())})
    assert status == 200 and first['status'] == 'ANSWERED', (status, first.get('code'))
    questions = first.get('suggested_questions', [])
    assert 2 <= len(questions) <= 3 and CLARIFY in questions, questions
    print('FOLLOWUP_FIRST_JSON=' + json.dumps(first, ensure_ascii=True), flush=True)
    status, before = request_json(f'/api/ai/conversations/{conversation_id}/', token)
    assert status == 200 and len(before['turns']) == 1
    payload = {**selector, 'question': CLARIFY, 'client_message_id': str(uuid.uuid4())}
    status, second = request_json('/api/ai/chat/', token, payload)
    assert status == 200 and second['status'] == 'ANSWERED', (status, second.get('code'))
    print('FOLLOWUP_SECOND_JSON=' + json.dumps(second, ensure_ascii=True), flush=True)
    status, replay = request_json('/api/ai/chat/', token, payload)
    # Restored responses add the latest feedback rating; answer/identity must be unchanged.
    assert status == 200 and {key: value for key, value in replay.items() if key != 'rating'} == second
    assert replay.get('rating') is None
    status, after = request_json(f'/api/ai/conversations/{conversation_id}/', token)
    assert status == 200 and len(after['turns']) == 2
    assert after['turns'][0]['result']['suggested_questions'] == questions
    assert first['conversation_id'] == second['conversation_id'] == conversation_id
    assert first['memory']['turns_used'] == 0 and second['memory']['turns_used'] >= 1
    assert CLARIFY not in second.get('suggested_questions', [])
    for result in (first, second):
        assert result['citations']
        for citation in result['citations']:
            chunk = runtime.catalog[citation['chunk_id']]
            assert chunk.document_id == str(document.pk) and chunk.version_id == str(document.published_version_id)
            assert chunk.text == citation['excerpt'] and chunk.page_number == citation['page_number']
    report = dict(status='FOLLOWUP_API_ACCEPTANCE_PASSED', gateway=gateway,
        document_id=str(document.pk), version_id=str(document.published_version_id),
        source_sha256=document.published_version.checksum_sha256,
        conversation_id=conversation_id, suggestions=questions, results=[first, second],
        before_click_turns=1, after_click_and_replay_turns=2, replay_matches=True,
        persisted_suggestions_match=True, source_identity_verified=True,
        scope='Owner API with real Qwen; frontend interactions covered separately. Not a benchmark.')
    print('FOLLOWUP_REPORT_JSON=' + json.dumps(report, ensure_ascii=True), flush=True)


def run_summary(scope, document, token, pages):
    status, job = request_json('/api/ai/chat/', token, {**scope, 'document_ids':[str(document.pk)],
        'mode':'summary', 'question':'Tóm tắt nội dung học liệu.', 'summary_request_id':str(uuid.uuid4()), **pages})
    if status != 202:
        return status, job
    for _ in range(120):
        status, job = request_json(f"/api/ai/summaries/{job['id']}/", token, {})
        print('SUMMARY_PROGRESS_JSON=' + json.dumps(job.get('progress'), ensure_ascii=True), flush=True)
        if status not in (200, 202) or job.get('status') == 'FAILED':
            return status, job
        if job.get('status') == 'COMPLETED':
            return 200, job['result']
        if job.get('status') == 'PROCESSING':
            time.sleep(2)
    raise RuntimeError('Summary did not finish within the step budget.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--health-only', action='store_true')
    parser.add_argument('--followups', action='store_true', help='Check suggested questions, selected follow-up and idempotent replay.')
    parser.add_argument('--summary', action='store_true', help='Check only coherent summaries, not QA/hints.')
    args = parser.parse_args()
    if not args.run and not args.health_only:
        print('Use --run to create two ordinary conversations and run real inference.')
        return
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.docker')
    import django
    django.setup()
    from apps.ai.runtime import get_runtime
    from apps.ai.services import map_output
    from apps.courses.models import CourseMember
    from apps.documents.models import KnowledgeDocument
    from rest_framework_simplejwt.tokens import AccessToken

    document = KnowledgeDocument.objects.select_related('published_version', 'session__classroom').get(
        pk='3724aa92-4a4a-4c61-9063-df2ce124540e', is_published=True, removed_at__isnull=True)
    version = document.published_version
    assert version.checksum_sha256 == '4544a1ece75d7f14e77cf2514ae156e7b2aa48bcd94321eaf43740808389aeb2'
    owner = CourseMember.objects.select_related('user').get(course=document.course, role='OWNER', status='ACTIVE', user__is_active=True)
    token = str(AccessToken.for_user(owner.user))
    scope = dict(course_id=str(document.course_id))
    if document.session_id:
        scope.update(session_id=str(document.session_id), classroom_id=str(document.session.classroom_id))
    runtime = get_runtime()
    gateway = check_gateway(runtime.config)
    if args.health_only:
        print(json.dumps(gateway))
        return
    if args.followups:
        check_followups(scope, document, token, runtime, gateway)
        return
    if args.summary and not (gateway['ready'] and gateway.get('summary_ready')):
        print('SUMMARY_NOT_RUN: import current runtime.ipynb, restart Python and run both code cells.')
        return
    report = dict(created_at=datetime.now(timezone.utc).isoformat(), document_id=str(document.pk),
        version_id=str(version.pk), source_sha256=version.checksum_sha256, cases=[],
        scope='Owner API memory/summary; hint uses real gateway with visible practice content, not a production assessment.')
    report['gateway'] = gateway
    report['generation_acceptance'] = 'RUNNING' if gateway['ready'] else 'NOT_RUN_GATEWAY_UNAVAILABLE'

    def record(name, status, result, expected_memory=None):
        citations = result.get('citations', [])
        matches = [bool((chunk := runtime.catalog.get(c.get('chunk_id'))) and
            chunk.document_id == str(document.pk) and chunk.version_id == str(version.pk)
            and chunk.page_number == c['page_number'] and chunk.text == c['excerpt']) for c in citations]
        memory = result.get('memory', {}).get('turns_used')
        checks = dict(http_200=status == 200, answered=result.get('status') == 'ANSWERED',
            source_identity=bool(citations) and all(matches))
        if expected_memory is not None:
            checks['memory_boundary'] = memory == 0 if expected_memory == 0 else isinstance(memory, int) and memory >= 1
        row = dict(id=name, http_status=status, checks=checks, result=result)
        report['cases'].append(row)
        print('STUDY_CASE_JSON=' + json.dumps(row, ensure_ascii=True), flush=True)

    scenarios = [
        [('conditions', 'Triết học ra đời trong những điều kiện nào? Trình bày đủ các điều kiện được giáo trình nêu.', 0),
         ('condition_followup', 'Giải thích rõ hơn điều kiện thứ hai.', 1),
         ('topic_change', 'Thế giới quan là gì và có những loại hình cơ bản nào?', 0)],
        [('independent', 'Vấn đề cơ bản của triết học có hai mặt nào?', 0),
         ('second_side', 'Mặt thứ hai nói về điều gì?', 1)],
    ]
    for scenario in scenarios if gateway['ready'] and not args.summary else []:
        status, conversation = request_json('/api/ai/conversations/', token, {**scope, 'document_id': str(document.pk)})
        assert status == 201, (status, conversation)
        for name, question, expected_memory in scenario:
            status, result = request_json('/api/ai/chat/', token, {**scope, 'document_ids': [str(document.pk)],
                'conversation_id': conversation['id'], 'client_message_id': str(uuid.uuid4()), 'question': question, 'mode': 'qa'})
            record(name, status, result, expected_memory)
    for name, pages in [('summary_pages', dict(page_start=4, page_end=6)), ('summary_document', {})]:
        status, result = run_summary(scope, document, token, pages)
        record(name, status, result)
    source = sorted([c for c in runtime.catalog.values() if c.version_id == str(version.pk) and c.page_number == 4], key=lambda c: c.chunk_order)
    contexts = [dict(source_id=f'S{i}', chunk_id=c.chunk_id, text=c.text, document_id=c.document_id,
        version_id=c.version_id, document_title=c.document_title, page_number=c.page_number, section_title=c.section_title)
        for i, c in enumerate(source, 1)]
    hint_cases = [('hint_read', 'Gợi ý cách đọc học liệu để tự trả lời bài tập.'),
                  ('hint_no_answer', 'Hãy đưa đáp án hoàn chỉnh cho tôi chép vào bài.')]
    for name, question in hint_cases if gateway['ready'] and not args.summary else []:
        started = time.monotonic()
        try:
            output = runtime.generate(question=question, mode='hint', contexts=contexts,
                exercise=dict(assessment_id=str(uuid.uuid4()), kind='TEXT', title='Ôn tập Triết học',
                    description='Trình bày những điều kiện ra đời của Triết học.', question=None), config=runtime.config)
            status, answer, citations = map_output(output, contexts)
            result = dict(status=status, answer=answer, citations=citations, seconds=round(time.monotonic()-started, 3))
            record(name, 200, result)
        except Exception as exc:
            record(name, 503, dict(code=getattr(exc, 'code', type(exc).__name__)))
    report['executed_checks_passed'] = all(all(row['checks'].values()) for row in report['cases'])
    report['expected_scenarios'] = 2 if args.summary else 9
    report['all_scenarios_executed'] = gateway['ready'] and len(report['cases']) == report['expected_scenarios']
    if gateway['ready']:
        report['generation_acceptance'] = 'EXECUTED_PENDING_SOURCE_REVIEW'
    report['semantic_review'] = 'PENDING_SOURCE_REVIEW'
    print('STUDY_REPORT_JSON=' + json.dumps(report, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
