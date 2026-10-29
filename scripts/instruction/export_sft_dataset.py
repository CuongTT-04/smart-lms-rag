"""Export reviewed candidates or fixture previews, not final peer-approved releases."""
import argparse
from collections import Counter
from pathlib import Path
import os
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from filelock import FileLock
from scripts.instruction.common import (canonical, check_internal_research, digest, guard_output, json_bytes, jsonl_bytes,
    load_resources, project_sft, read_json, read_jsonl, read_reviews, require, validate_records, validate_reviews)

SPLITS = ('train', 'validation', 'instruction_holdout')


def connected_components(records):
    by_id = {record['record_id']: record for record in records}
    require(len(by_id) == len(records), 'DUPLICATE_RECORD_ID')
    parents = {key: key for key in by_id}

    def find(key):
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    owners = {}
    for key, record in by_id.items():
        groups = [('source', value) for value in record['source_group_ids']]
        groups += [('document', item['document_id']) for item in record['contexts']]
        groups.append(('variant', record['variant_family_id']))
        for group in groups:
            if group in owners:
                parents[find(key)] = find(owners[group])
            owners[group] = key
        parent = record['parent_record_id']
        if parent is not None:
            require(parent in by_id, 'PARENT_NOT_INCLUDED')
            parents[find(key)] = find(parent)
    components = {}
    for key in by_id:
        component = find(key)
        components.setdefault(component, []).append(key)
    return sorted((sorted(ids) for ids in components.values()), key=lambda ids: ids[0])


def validate_plan(records, plan, contract):
    require(isinstance(plan, dict) and set(plan) == {'seed','assignments','record_hashes'}, 'INVALID_SPLIT_PLAN')
    require(type(plan['seed']) is int and plan['seed'] == contract['split']['seed'], 'SPLIT_SEED_CHANGED')
    require(isinstance(plan['assignments'], dict) and isinstance(plan['record_hashes'], dict), 'INVALID_SPLIT_PLAN')
    by_id = {record['record_id']: record for record in records}
    require(set(plan['assignments']) == set(by_id) == set(plan['record_hashes']), 'SPLIT_ID_MISMATCH')
    for key, record in by_id.items():
        require(plan['record_hashes'][key] == record['content_sha256'], 'STALE_SPLIT_HASH')
        require(plan['assignments'][key] in SPLITS, 'UNKNOWN_SPLIT')
    components = connected_components(records)
    for ids in components:
        require(len({plan['assignments'][key] for key in ids}) == 1, 'SPLIT_GROUP_LEAKAGE')
    counts = Counter(plan['assignments'].values())
    require(all(counts[name] > 0 for name in SPLITS), 'EMPTY_SPLIT')
    return dict(counts), len(components)


def export(records, reviews, plan, output, resources, *, preview=False, input_paths=(), internal_research=False):
    output = guard_output(output, input_paths)
    if internal_research:
        require(not preview, 'RESEARCH_IS_NOT_FIXTURE')
        check_internal_research(resources)
        require(output.is_relative_to((resources.root/'.private/instruction').resolve()),
                'RESEARCH_OUTPUT_MUST_STAY_PRIVATE')
    rows = sorted(records, key=lambda row: row['record_id'])
    validate_records(rows, resources, preview=preview, private_draft=internal_research)
    accepted = validate_reviews(rows, reviews, resources)
    counts, components = validate_plan(rows, plan, resources.contract)
    payloads = {}
    for split in SPLITS:
        payloads[split + '.jsonl'] = jsonl_bytes([
            project_sft(row, resources, preview=preview, private_draft=internal_research) for row in rows
            if plan['assignments'][row['record_id']] == split])
    payloads['metadata.jsonl'] = jsonl_bytes([
        {'record_id': row['record_id'], 'content_sha256': row['content_sha256'],
         'split': plan['assignments'][row['record_id']],
         'row_index': sum(1 for old in rows[:index] if plan['assignments'][old['record_id']] == plan['assignments'][row['record_id']]),
         'record': row, 'self_review': accepted[row['record_id']]}
        for index, row in enumerate(rows)])
    manifest = {
        'schema_version': 1,
        'status': ('INTERNAL_RESEARCH_CANDIDATE_PENDING_AUDIT' if internal_research else
                   'FIXTURE_PREVIEW_NOT_DATASET' if preview else 'CANDIDATE_PENDING_B_REVIEW'),
        'scope': 'PRIVATE_INTERNAL_RESEARCH' if internal_research else 'STANDARD',
        'source_rights_status': resources.contract['source_rights']['status'],
        'research_decision': resources.contract['source_rights'].get('internal_research') if internal_research else None,
        'rights_verified_by_export': False,
        'public_redistribution_allowed': False,
        'training_ready': False,
        'record_count': len(rows), 'real_dataset_record_count': 0 if preview else len(rows),
        'target_accepted_total': resources.contract['targets']['accepted_total'],
        'full_target_peer_accepted': False,
        'split_counts': counts, 'component_count': components,
        'task_counts': dict(Counter(row['task_type'] for row in rows)),
        'course_counts': dict(Counter(row['course_code'] for row in rows)),
        'input_sha256': {'records': digest(jsonl_bytes(rows)),
                         'reviews': digest(canonical(sorted(reviews, key=lambda row: canonical(row)))),
                         'split_plan': digest(canonical(plan)),
                         'contract': digest(canonical(resources.contract)),
                         'schema': digest(canonical(resources.schema))},
        'model_id': resources.contract['format']['model_id'],
        'model_revision': resources.contract['format']['model_revision'],
        'prompt_version': resources.contract['format']['prompt_version'],
        'prompt_builder_sha256': digest((ROOT/'backend/apps/ai/rag/context_builder.py').read_bytes()),
        'validation': {'schema_and_target_format': 'PASSED',
                       'source_integrity': 'VIRTUAL_FIXTURE_ONLY' if preview else 'PASSED',
                       'benchmark_questions': 'EXACT_AND_NEAR_DUPLICATE_SCREENING',
                       'semantic_grounding': 'REQUIRES_FINAL_PEER_REVIEW',
                       'tokenizer_eos_loss_mask': 'NOT_RUN',
                       'training': 'NOT_RUN', 'final_b_review': 'PENDING'},
        'model_calls': 0, 'quality_verified': False,
        'benchmark_input_integrity': resources.benchmark_integrity,
        'limitation': 'Self-review and structural checks do not establish semantic quality. No final release, training, or measured token budget is certified.',
        'files': {name: {'sha256': digest(data), 'size_bytes': len(data)} for name, data in payloads.items()},
    }
    payloads['manifest.json'] = json_bytes(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(output) + '.lock', timeout=10):
        require(not output.exists(), 'OUTPUT_ALREADY_EXISTS')
        temporary = Path(tempfile.mkdtemp(prefix='.' + output.name + '-', dir=output.parent))
        try:
            for name, data in payloads.items():
                (temporary/name).write_bytes(data)
            require(not output.exists(), 'OUTPUT_ALREADY_EXISTS')
            os.rename(temporary, output)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, nargs='+', required=True)
    parser.add_argument('--reviews', type=Path, required=True, help='CSV or JSONL review rows; no automatic approvals.')
    parser.add_argument('--split-plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--contract', type=Path, default=ROOT/'data/instruction/input-contract.json')
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--preview', action='store_true', help='Fixture-only preview; excluded from real dataset counts.')
    parser.add_argument('--internal-research', action='store_true', help='Explicit project exception for private research; rights remain unverified and technical audits remain required.')
    args = parser.parse_args(argv)
    try:
        inputs = [*args.inputs, args.reviews, args.split_plan, args.contract, *([args.bundle] if args.bundle else [])]
        guard_output(args.output, inputs)
        records = [row for path in args.inputs for row in read_jsonl(path)]
        manifest = export(records, read_reviews(args.reviews), read_json(args.split_plan), args.output,
                          load_resources(args.contract, preview=args.preview, bundle=args.bundle),
                          preview=args.preview, input_paths=inputs, internal_research=args.internal_research)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'{type(error).__name__}: {error}\n')
    print(manifest['status'], manifest['record_count'], 'records; model_calls=0')


if __name__ == '__main__':
    main()
