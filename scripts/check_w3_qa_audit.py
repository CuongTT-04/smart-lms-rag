"""Check audited QA artifacts, CSV/JSON parity and deterministic regeneration."""

from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    assert rows and all(None not in row and None not in row.values() for row in rows), path
    return rows


def main():
    qa = ROOT/'data/qa'
    rows = read_csv(qa/'qa_baseline.csv')
    audit = read_csv(qa/'qa_source_audit.csv')
    log = read_csv(qa/'qa_review_log.csv')
    data = json.loads((qa/'qa_baseline.json').read_text(encoding='utf-8'))
    cases = {row['qa_id']: row for row in data['cases']}
    assert len(rows) == len(cases) == len(audit) == len(log) == 100
    assert len({row['qa_id'] for row in rows}) == 100
    assert set(cases) == {row['qa_id'] for row in audit} == {row['qa_id'] for row in log}
    questions = [re.sub(r'\s+', ' ', row['question']).strip().casefold() for row in rows]
    assert len(set(questions)) == 100
    for row in rows:
        case = cases[row['qa_id']]
        assert all(row[field] == case[field] for field in ('question', 'ground_truth', 'mode'))
        pages = json.loads(row['source_pages'])
        assert case['gold_sources'] == [{'document_id': row['document_id'], 'version_id': row['version_id'], 'page_number': p} for p in pages]
        assert row['source_check'] == 'source_checked_pending_peer'
        if row['question_type'] == 'true_false':
            assert row['ground_truth'] in ('True', 'False')
        if row['question_type'] == 'multiple_choice':
            assert row['ground_truth'] in re.findall(r'\b([A-D])\)', row['question'])
        assert (row['mode'] == 'hint') == (row['question_type'] == 'hint')
    assert all(row['peer_review_status'] == 'pending' and not row['peer_reviewer'] for row in log)
    assert all(row['agent_reviewer'] == 'Codex' and row['evidence_excerpt'] for row in audit)
    assert data['review_status'] == 'pending_human_peer'
    special = next(row for row in rows if row['qa_id'] == 'KTCTMLN_QA_001')
    assert special['source_doc'] == 'ch01.pdf' and json.loads(special['source_pages']) == [20]
    assert json.loads(next(row for row in rows if row['qa_id'] == 'KTCTMLN_QA_005')['source_pages']) == [10]
    modified = [row['qa_id'] for row in audit if json.loads(row['changes'])]
    assert modified == ['KTCTMLN_QA_005', 'CNXHKH_QA_018']
    inputs = ['qa_pilot_v1.0.csv', 'qa_pilot_v2.0.csv', 'qa_contributions.csv']
    original = {name: (qa/name).read_bytes() for name in inputs}
    names = ['qa_baseline.csv', 'qa_baseline.json', 'qa_review_log.csv', 'qa_source_audit.csv', 'source_map.json']
    before = {name: (qa/name).read_bytes() for name in names}
    spec = importlib.util.spec_from_file_location('qa_merge_verified', ROOT/'scripts/merge_w3_qa.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    summary = module.build(ROOT/'data/corpus', qa)
    assert all((qa/name).read_bytes() == value for name, value in before.items())
    assert all((qa/name).read_bytes() == value for name, value in original.items())
    report = {'verified_date': '2026-10-15', 'status': 'PASSED_AGENT_AUDIT', **summary,
              'course_counts': dict(Counter(row['course_id'] for row in rows)),
              'mode_counts': dict(Counter(row['mode'] for row in rows)),
              'csv_json_parity': True, 'deterministic_regeneration': True,
              'pilot_and_b_inputs_unchanged': True, 'editorially_changed_qa': modified,
              'special_qa': {'qa_id': 'KTCTMLN_QA_001', 'source_doc': 'KTCTMLN/ch01.pdf',
                             'physical_page': 20, 'question_answer_and_page_unchanged': True,
                             'source_evidence_verified': True, 'human_peer_approved': False},
              'dataset_sha256': hashlib.sha256((qa/'qa_baseline.json').read_bytes()).hexdigest(),
              'outputs_sha256': {name: hashlib.sha256((qa/name).read_bytes()).hexdigest() for name in names},
              'limitation': 'Agent-assisted content/source audit, not human peer approval; no predictions used to modify gold. No claim of semantic independence or model quality.'}
    directory = ROOT/'docs/reports'
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'w3-qa-source-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
