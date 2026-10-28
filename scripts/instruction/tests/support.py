from copy import deepcopy
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from scripts.instruction.common import ROOT, Resources, content_hash, digest, read_json


def resources():
    return Resources(read_json(ROOT/'data/instruction/input-contract.json'),
                     read_json(ROOT/'data/instruction/record-schema.json'))


def record(number=1, task='qa'):
    questions = {
        1: 'Người học cần ghi lại nội dung gì sau khi đọc?',
        2: 'Tóm tắt quy trình chuẩn bị thảo luận.',
        3: 'Hướng dẫn cách tìm mục đích của việc ghi chép.',
        4: 'Khóa học yêu cầu học phí bao nhiêu?',
        5: 'Buổi trao đổi tiếp theo sử dụng những ghi chú nào?',
        6: 'Nêu ngắn gọn vai trò của câu hỏi còn thắc mắc.',
    }
    text = 'Sau khi đọc, học viên ghi một điều đã hiểu và một câu hỏi để chuẩn bị trao đổi.'
    context = {'source_id': 'S1', 'chunk_id': f'fixture-{number}', 'text': text,
               'document_id': str(uuid5(NAMESPACE_URL, f'fixture-doc-{number}')),
               'version_id': str(uuid5(NAMESPACE_URL, f'fixture-version-{number}')),
               'document_title': 'Nguồn tự biên soạn dùng trong unit test',
               'page_number': 1, 'section_title': None,
               'source_checksum': digest(text.encode('utf-8')),
               'text_sha256': digest(text.encode('utf-8')),
               'rights_reference': 'FIXTURE:self-authored'}
    target = {'qa': 'Học viên ghi một điều đã hiểu và một câu hỏi để chuẩn bị trao đổi [1].',
              'summary': 'Học viên đọc, ghi chú và chuẩn bị trao đổi [1].',
              'hint': 'READ [1]', 'insufficient_evidence': 'INSUFFICIENT_EVIDENCE'}[task]
    row = {'schema_version': 'w5-instruction-v1', 'record_id': f'FX_W5_{number:05d}',
           'author_member': 'A', 'course_code': 'FIXTURE', 'language': 'vi',
           'task_type': task, 'mode': 'hint' if task == 'hint' else 'qa',
           'question': questions[number], 'contexts': [context], 'exercise': None,
           'target_text': target, 'source_group_ids': [f'FIXTURE:source-{number}'],
           'variant_family_id': f'FIXTURE_FAMILY_{number}', 'parent_record_id': None,
           'provenance': {'method': 'manual', 'drafting_tool': None, 'generation_model_id': None,
                          'generation_model_revision': None, 'generation_prompt_sha256': None,
                          'recipe_id': 'unit-test-only', 'created_at': '2026-10-28T09:00:00+07:00'},
           'prompt_version': 'bounded_guidance', 'source_identity_scope': 'fixture_only'}
    return rehash(row)


def rehash(row):
    row['content_sha256'] = content_hash(row)
    return row


def draft(row):
    return {key: deepcopy(value) for key, value in row.items() if key not in ('record_id','content_sha256')}


def reviews(rows):
    return [{'record_id': row['record_id'], 'content_sha256': row['content_sha256'],
             'reviewer_member': row['author_member'], 'review_kind': 'SELF_REVIEW',
             'reviewed_at': '2026-10-28T10:00:00+07:00', 'instruction_clarity': 2,
             'content_correctness': 2, 'grounding_and_citation': 2, 'task_behavior': 2,
             'language_and_format': 2, 'decision': 'ACCEPT',
             'reason': 'Synthetic review row for unit test, not a dataset approval.', 're_review_of': None}
            for row in rows]


def plan(rows):
    splits = ['train','validation','instruction_holdout']
    return {'seed':42, 'assignments': {row['record_id']:splits[index % 3] for index,row in enumerate(rows)},
            'record_hashes': {row['record_id']:row['content_sha256'] for row in rows}}


def production_resource(folder):
    res = resources()
    res.root = Path(folder)
    row = record()
    row.update(record_id='W5_A_00001',course_code='THMLN',source_identity_scope='offline_corpus',
               source_group_ids=['THMLN:ch01.pdf'])
    path = res.root/'source.pdf'
    path.write_bytes(b'unit test PDF bytes; extraction is mocked explicitly')
    context = row['contexts'][0]
    context.update(source_checksum=digest(path.read_bytes()),rights_reference='unit-test-source-permission')
    res.sources = [{'document_id':context['document_id'], 'version_id':context['version_id'],
                    'source_group_id':'THMLN:ch01.pdf','course_code':'THMLN', 'source_doc':'ch01.pdf',
                    'source_checksum':context['source_checksum'],'relative_path':'source.pdf',
                    'generation_authorized':True,'rights_status':'VERIFIED_TEST_DOUBLE',
                    'rights_evidence_reference':'unit-test-source-permission','page_count':1}]
    res.__post_init__()
    return rehash(row),res
