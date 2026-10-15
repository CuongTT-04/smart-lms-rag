"""Merge A75+B50 into 100 distinct development QA; preserve pending human review."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    ids = [row['qa_id'] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate QA ID in input.')
    return rows


def merge_rows(a_rows, b_rows):
    result = {row['qa_id']: dict(row) for row in a_rows}
    for row in b_rows:
        old = result.get(row['qa_id'])
        if old and any(old[field] != row[field] for field in
                       ('course_id', 'question', 'ground_truth', 'source_doc', 'source_page')):
            raise ValueError(f'Conflicting shared QA: {row["qa_id"]}')
        result[row['qa_id']] = dict(row)
    questions = [re.sub(r'\s+', ' ', row['question']).strip().casefold() for row in result.values()]
    if len(questions) != len(set(questions)):
        raise ValueError('Duplicate normalized question.')
    return list(result.values())


def compact(text):
    return unicodedata.normalize('NFC', re.sub(r'\s+', '', unicodedata.normalize('NFC', text))).casefold()


def audit_rows(rows, sources, qa, corpus):
    """Apply explicit editorial corrections and verify source evidence, not human approval."""
    specs = {}
    for name in ('qa_pilot_v2.0_corrections.json', 'qa_pilot_v2.0_additions.json'):
        for item in json.loads((qa/name).read_text(encoding='utf-8'))['rows']:
            specs[item['qa_id']] = {'anchor': item['evidence_anchor'], 'terms': item['evidence_terms']}
    for item in json.loads((qa/'qa_w3_source_checks.json').read_text(encoding='utf-8'))['checks']:
        if item['qa_id'] in specs:
            raise ValueError('Duplicate evidence specification: '+item['qa_id'])
        specs[item['qa_id']] = item
    if set(specs) != {row['qa_id'] for row in rows}:
        raise ValueError('Evidence specifications must cover exactly the merged QA IDs.')
    readers, evidence, revised = {}, [], []
    for original in rows:
        row = dict(original)
        spec = specs[row['qa_id']]
        changes = spec.get('changes', {})
        if set(changes) - {'question', 'ground_truth', 'source_page', 'source_pages', 'notes', 'source_section'}:
            raise ValueError('Unsupported editorial correction fields.')
        row.update(changes)
        key = (row['course_id'], row['source_doc'])
        path = Path(corpus)/key[0]/key[1]
        if key not in readers:
            readers[key] = PdfReader(path)
        reader = readers[key]
        pages = json.loads(row.get('source_pages') or '['+row['source_page']+']')
        if (not isinstance(pages, list) or not pages or any(type(p) is not int or not 1 <= p <= len(reader.pages) for p in pages)
                or len(set(pages)) != len(pages) or int(row['source_page']) != pages[0]):
            raise ValueError('Invalid gold pages: '+row['qa_id'])
        texts = [unicodedata.normalize('NFC', re.sub(r'\s+', ' ', reader.pages[p-1].extract_text() or '').strip()) for p in pages]
        joined = '\n'.join(texts)
        missing = [term for term in [spec['anchor'], *spec['terms']] if compact(term) not in compact(joined)]
        if missing:
            raise ValueError(f"Missing source evidence for {row['qa_id']}: {missing}")
        source = sources[key]
        evidence.append({'qa_id': row['qa_id'], 'course_code': key[0], 'source_doc': key[1],
                         'source_pages': json.dumps(pages), 'source_checksum': source['source_checksum'],
                         'agent_reviewer': 'Codex', 'audit_status': 'agent_source_checked_pending_human_peer',
                         'evidence_anchor': spec['anchor'], 'evidence_terms': json.dumps(spec['terms'], ensure_ascii=False),
                         'evidence_excerpt': joined,
                         'changes': json.dumps({k: {'before': original.get(k, ''), 'after': v} for k, v in changes.items() if original.get(k, '') != v}, ensure_ascii=False),
                         'note': spec.get('note', 'Đối chiếu câu hỏi/đáp án và bằng chứng trang nguồn; không thay thế human peer review.')})
        revised.append(row)
    return revised, evidence


def build(corpus, output):
    qa = ROOT / 'data/qa'
    existing_log = Path(output)/'qa_review_log.csv'
    if existing_log.exists():
        previous_reviews = read_csv(existing_log)
        if any(r.get('peer_review_status', 'pending') not in ('', 'pending') or r.get('peer_reviewer', '').strip() for r in previous_reviews):
            raise ValueError('Existing human review must be reconciled explicitly; refusing to reset peer decisions.')
    a, b = read_csv(qa/'qa_pilot_v2.0.csv'), read_csv(qa/'qa_w3_cuong_v1.0.csv')
    rows = merge_rows(a, b)
    if len(rows) != 100:
        raise ValueError('Expected 100 distinct development QA.')
    reviews_a = {r['qa_id']: r for r in read_csv(qa/'qa_pilot_v2.0_review.csv')}
    b_ids = {r['qa_id'] for r in b}
    sources = {}
    for path in sorted(Path(corpus).glob('*/*.pdf')):
        code = path.parent.name
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        document = str(uuid5(NAMESPACE_URL, 'w3-document:'+code+'/'+path.name))
        sources[(code, path.name)] = {
            'course_code': code, 'source_doc': path.name,
            'course_id': str(uuid5(NAMESPACE_URL, 'w3-course:'+code)),
            'document_id': document,
            'version_id': str(uuid5(NAMESPACE_URL, document+':'+checksum)),
            'source_checksum': checksum,
            'page_count': len(PdfReader(path).pages),
        }
    rows, evidence = audit_rows(rows, sources, qa, corpus)
    rows = merge_rows(rows, [])
    audit_by_id = {item['qa_id']: item for item in evidence}
    cases, review_log, merged = [], [], []
    fields = list(a[0]) + ['mode', 'owner', 'source_checksum', 'document_id', 'version_id',
                           'source_pages', 'source_check', 'peer_review_status']
    for row in rows:
        source = sources[(row['course_id'], row['source_doc'])]
        pages = json.loads(row.get('source_pages') or '['+row['source_page']+']')
        if (not isinstance(pages, list) or not pages or len(pages) != len(set(pages))
                or any(type(p) is not int or not 1 <= p <= source['page_count'] for p in pages)):
            raise ValueError('Invalid physical page labels: '+row['qa_id'])
        review_a = reviews_a.get(row['qa_id'], {})
        checksum = row.get('source_checksum') or review_a.get('source_sha256')
        if checksum and checksum != source['source_checksum']:
            raise ValueError('QA evidence checksum differs from corpus: '+row['qa_id'])
        for key in ('document_id', 'version_id'):
            if row.get(key) and row[key] != source[key]:
                raise ValueError('QA UUID mapping differs from corpus: '+row['qa_id'])
        checked = row['qa_id'] in audit_by_id
        owner = 'Cường' if row['qa_id'] in b_ids else ('Dương' if review_a else 'Nhóm (pilot còn lại)')
        status = 'source_checked_pending_peer' if checked else 'source_review_required'
        values = {key: row.get(key, '') for key in fields}
        values.update(mode=row.get('mode') or 'qa', owner=owner, source_checksum=source['source_checksum'],
                      document_id=source['document_id'], version_id=source['version_id'],
                      source_pages=json.dumps(pages), source_check=status, peer_review_status='pending')
        merged.append(values)
        cases.append({'qa_id': row['qa_id'], 'question': row['question'], 'mode': values['mode'],
                      'ground_truth': row['ground_truth'], 'course_id': source['course_id'],
                      'gold_sources': [{'document_id': source['document_id'], 'version_id': source['version_id'],
                                        'page_number': page} for page in pages],
                      'evidence_reference': 'data/qa/qa_w3_source_audit.csv#'+row['qa_id']})
        review_log.append({'qa_id': row['qa_id'], 'owner': owner, 'source_doc': row['source_doc'],
                           'source_pages': json.dumps(pages), 'source_checksum': source['source_checksum'],
                           'source_check': status, 'peer_reviewer': '', 'peer_review_status': 'pending',
                           'agent_reviewer': 'Codex', 'agent_review_status': 'source_checked',
                           'evidence_reference': 'data/qa/qa_w3_source_audit.csv#'+row['qa_id'],
                           'note': audit_by_id[row['qa_id']]['note']})
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, values in [('qa_w3_v1.0.csv', merged), ('qa_review_log.csv', review_log), ('qa_w3_source_audit.csv', evidence)]:
        with (output/name).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(values)
    for name, data in [('qa_w3_v1.0.json', {'cases': cases, 'review_status': 'pending_human_peer'}),
                       ('w3_source_map.json', {'page_unit': 'physical_pdf_1based', 'sources': list(sources.values())})]:
        (output/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return {'a_rows': len(a), 'b_rows': len(b), 'shared_ids': len(a)+len(b)-len(rows),
            'merged_qa': len(rows), 'source_checked_pending_peer': sum(r['source_check'].startswith('source_checked') for r in merged),
            'source_review_required': [r['qa_id'] for r in merged if r['source_check']=='source_review_required'],
            'human_peer_approved': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=ROOT/'data/corpus')
    parser.add_argument('--output', type=Path, default=ROOT/'data/qa')
    args = parser.parse_args()
    print(json.dumps(build(args.corpus, args.output), ensure_ascii=False, indent=2))
