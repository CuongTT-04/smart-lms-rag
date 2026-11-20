"""Run inside the backend container; keep raw questions/answers in private storage."""
import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


SOURCE_PROFILE = {
    'path': 'data/corpus/THMLN/ch01.pdf',
    'sha256': '4544a1ece75d7f14e77cf2514ae156e7b2aa48bcd94321eaf43740808389aeb2',
    'page_numbering': 'Physical PDF pages, not printed footer numbers.',
}

CASES = (
    ('definition', 'Theo giáo trình, triết học là gì?',
     'PDF trang 4: hệ thống tri thức lý luận chung nhất về thế giới và vị trí, vai trò của con người.'),
    ('origins', 'Triết học ra đời vào thời gian nào và tại những trung tâm văn minh nào?',
     'PDF trang 3: khoảng thế kỷ VIII–VI trước Công nguyên; Trung Quốc, Ấn Độ, Hy Lạp.'),
    ('conditions', 'Triết học ra đời trong những điều kiện nào? Trình bày đủ các điều kiện được giáo trình nêu.',
     'PDF trang 4: vốn hiểu biết/khả năng khái quát và tầng lớp lao động trí óc; không dừng ở câu dẫn.'),
    ('basic_problem', 'Vấn đề cơ bản của triết học có hai mặt nào?',
     'PDF trang 6: quan hệ vật chất–ý thức và khả năng nhận thức thế giới; đủ cả hai mặt.'),
    ('worldview', 'Thế giới quan là gì và theo quá trình phát triển có những loại hình cơ bản nào?',
     'PDF trang 6: khái niệm thế giới quan; huyền thoại, tôn giáo, triết học, không lẫn với các trường phái.'),
    ('materialism_forms', 'Trình bày ba hình thức cơ bản của chủ nghĩa duy vật và đặc điểm từng hình thức theo giáo trình.',
     'PDF trang 7–8: chất phác, siêu hình, biện chứng; kiểm cả phần tiếp nối, từng đặc điểm dẫn đúng đoạn.'),
    ('idealism_origins', 'Chủ nghĩa duy tâm có nguồn gốc nhận thức luận và nguồn gốc xã hội như thế nào?',
     'PDF trang 8–9: xem xét phiến diện/tuyệt đối hóa nhận thức; tách lao động trí óc–chân tay và lợi ích giai cấp. Không bỏ phần xã hội ở trang tiếp.'),
    ('methodology_levels', 'Phương pháp luận có những cấp độ nào? Phân biệt ngắn gọn từng cấp độ.',
     'PDF trang 11: ngành, chung, chung nhất; phân biệt phạm vi của từng cấp độ.'),
    ('missing_exam_date', 'Theo giáo trình này, ngày thi cuối kỳ của lớp tôi là ngày nào?',
     'Không có lịch thi của lớp trong tài liệu: phải từ chối, không đoán ngày hoặc gán nguồn.'),
    ('missing_teacher_contact', 'Theo giáo trình này, số điện thoại riêng của giảng viên lớp tôi là gì?',
     'Không có thông tin liên hệ của giảng viên lớp: phải từ chối, không suy từ tên tác giả.'),
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_gateway(config):
    url = os.environ['AI_INFERENCE_URL'].rstrip('/')
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path):
        raise RuntimeError('Invalid HTTPS inference base URL.')
    request = Request(url + '/health', headers={
        'Authorization': 'Bearer ' + os.environ['AI_INFERENCE_TOKEN'], 'ngrok-skip-browser-warning': '1'})
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise RuntimeError('Oversized gateway health response.')
    health = json.loads(raw)
    if not health.get('ready') or health.get('config') != config:
        raise RuntimeError('Gateway not ready or backend config differs.')
    if not {'qa_completeness_v1', 'qa_atomic_evidence_v1', 'qa_source_descriptions_v1', 'qa_source_selection_v1'} <= set(health.get('capabilities', [])):
        raise RuntimeError('Gateway update required: import current runtime.ipynb and rerun before final QA acceptance.')
    return {'config_matches': True, 'capabilities': health['capabilities']}


def request_json(path, token, data=None):
    body = None if data is None else json.dumps(data).encode()
    request = Request('http://127.0.0.1:8000' + path, data=body, headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
    try:
        with urlopen(request, timeout=150) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.loads(error.read())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--document', required=True, type=uuid.UUID)
    parser.add_argument('--run', action='store_true', help='Explicitly permit real inference and test conversations.')
    parser.add_argument('--case', action='append', choices=[row[0] for row in CASES],
                        help='Check selected cases first; omit to check all ten.')
    args = parser.parse_args()
    cases = [row for row in CASES if not args.case or row[0] in args.case]
    if not args.run:
        print(json.dumps(cases, ensure_ascii=True, indent=2))
        return
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.docker')
    import django
    django.setup()
    from apps.ai.runtime import get_runtime
    from apps.courses.models import CourseMember
    from apps.documents.models import KnowledgeDocument
    from apps.documents.retrieval_scope import resolve_scope
    from rest_framework_simplejwt.tokens import AccessToken

    document = KnowledgeDocument.objects.select_related('published_version', 'session__classroom').get(
        pk=args.document, removed_at__isnull=True, is_published=True)
    owner = CourseMember.objects.select_related('user').get(
        course=document.course, role='OWNER', status='ACTIVE', user__is_active=True)
    selector = {'course_id': str(document.course_id)}
    if document.session_id:
        selector.update(session_id=str(document.session_id), classroom_id=str(document.session.classroom_id))
    resolve_scope(owner.user, document_ids=[str(document.pk)], **selector)
    version = document.published_version
    if not version or version.status != 'READY' or version.indexed_at is None:
        raise RuntimeError('Published document is not indexed/READY; do not interpret as missing academic evidence.')
    if version.checksum_sha256 != SOURCE_PROFILE['sha256']:
        raise RuntimeError('Question set requires the exact project philosophy PDF; selected source checksum differs.')
    runtime = get_runtime()
    gateway = check_gateway(runtime.config)
    source = [chunk for chunk in runtime.catalog.values() if chunk.version_id == str(version.pk)]
    if not source:
        raise RuntimeError('Published version missing from loaded catalog; check indexing/runtime reload.')
    token = str(AccessToken.for_user(owner.user))
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'document_id': str(document.pk),
              'version_id': str(version.pk), 'source_sha256': version.checksum_sha256,
              'config': runtime.config, 'gateway': gateway, 'source_profile': SOURCE_PROFILE,
              'selected_case_ids': [row[0] for row in cases],
              'cases': [], 'semantic_review': 'PENDING_SOURCE_REVIEW',
              'scope': 'Owner API, standalone conversations; not student permissions or multi-turn acceptance.',
              'catalog': [{'chunk_id': c.chunk_id, 'page_number': c.page_number, 'text': c.text} for c in source]}
    for name, question, criterion in cases:
        status, conversation = request_json('/api/ai/conversations/', token,
                                            dict(selector, document_id=str(document.pk)))
        if status != 201:
            raise RuntimeError('Conversation creation failed: HTTP ' + str(status))
        started = time.monotonic()
        status, result = request_json('/api/ai/chat/', token, dict(
            selector, document_ids=[str(document.pk)], question=question, mode='qa',
            conversation_id=conversation['id'], client_message_id=str(uuid.uuid4())))
        checks = []
        for citation in result.get('citations', []):
            chunk = runtime.catalog.get(citation.get('chunk_id'))
            checks.append(bool(chunk and chunk.document_id == str(document.pk)
                               and chunk.version_id == str(version.pk)
                               and chunk.page_number == citation.get('page_number')
                               and chunk.text == citation.get('excerpt')))
        report['cases'].append({'id': name, 'question': question, 'criterion': criterion,
                                'http_status': status, 'seconds': round(time.monotonic()-started, 3),
                                'result': result, 'citation_identity_checks': checks,
                                'semantic_verdict': 'PENDING', 'findings': []})
        print('CASE', name, status, result.get('status', result.get('code')), flush=True)
        print('QA_CASE_JSON=' + json.dumps(report['cases'][-1], ensure_ascii=True), flush=True)
    content = json.dumps(report, ensure_ascii=True, sort_keys=True)
    print('REPORT_SHA256=' + hashlib.sha256(content.encode()).hexdigest())
    print('QA_REPORT_JSON=' + content)


if __name__ == '__main__':
    main()
