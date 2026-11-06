"""Combine authenticated W5 rows and member additions into a private technical candidate."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from scripts.qlora.data import digest, read_json, read_rows, require, sha_file, tokenize_payload
from scripts.qlora.runtime import inventory, verify_inventory, write_json
from scripts.instruction.expand import audit_package, load_tokenizer, scan_duplicates, SPLITS
from scripts.w6.contracts import load_archive


def bind_rows(inherited, additions):
    result = {split: [] for split in SPLITS}
    ids, groups, families = set(), {}, {}
    for row in [*inherited, *additions]:
        meta = row['metadata']
        rid, split = meta['record_id'], meta['split']
        require(rid not in ids, 'DUPLICATE_ID')
        ids.add(rid)
        require(split in result, 'UNKNOWN_SPLIT')
        require(digest(row['payload']) == meta['sft_sha256'], 'PAYLOAD_BINDING')
        for group in meta['source_group_ids']:
            require(group not in groups or groups[group] == split, 'GROUP_SPLIT_LEAKAGE')
            groups[group] = split
        family = meta['variant_family_id']
        require(family not in families or families[family] == split, 'FAMILY_SPLIT_LEAKAGE')
        families[family] = split
        result[split].append(row)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-compact', type=Path, required=True)
    parser.add_argument('--member-a', type=Path, required=True)
    parser.add_argument('--member-b', type=Path, required=True)
    parser.add_argument('--handoff', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    require(args.output.resolve().is_relative_to(root / '.private') and not args.output.exists(), 'NEW_PRIVATE_OUTPUT_REQUIRED')
    contract = read_json(args.handoff / 'data/pilot-v2/training-contract.json')
    original = load_archive(args.old_compact, contract['expected_compact'])
    tokenizer = load_tokenizer(args.handoff, contract)
    with (args.handoff / 'source/data/w6/record-allocation.csv').open(encoding='utf-8-sig', newline='') as stream:
        slots = list(csv.DictReader(stream))
    added, candidates, member_reports = [], [], {}
    for member, folder in [('A', args.member_a), ('B', args.member_b)]:
        member_reports[member] = audit_package(folder, tokenizer, contract, slots,
            [row['metadata'] for row in original['records']], member=member)
        candidates.extend(read_rows(folder / 'candidates.jsonl'))
        for split in SPLITS:
            payloads, metadata = read_rows(folder / (split + '.jsonl')), read_rows(folder / (split + '.metadata.jsonl'))
            added.extend(dict(payload=payload, metadata=meta) for payload, meta in zip(payloads, metadata))
    old_records = [dict(record_id=row['metadata']['record_id'], question=json.loads(row['payload']['prompt'][-1]['content'])['question'],
                        target_text=row['payload']['completion'][0]['content']) for row in original['records']]
    findings, _ = scan_duplicates(candidates, old_records, read_json(root / 'data/instruction/w5/contract/benchmark-exclusion-manifest.json'))
    require(not findings, 'GROUP_DUPLICATE_FINDINGS:' + json.dumps(findings[:3], ensure_ascii=False))
    splits = bind_rows(original['records'], added)
    require({key: len(rows) for key, rows in splits.items()} == dict(train=770, validation=114, instruction_holdout=116), 'GROUP_1000_COUNTS')
    args.output.mkdir(parents=True)
    stats, checks = {}, []
    def rows_file(name, rows):
        (args.output / name).write_text(''.join(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n' for row in rows), encoding='utf-8')
    for split, rows in splits.items():
        metas, tokenized = [], []
        for index, row in enumerate(rows):
            meta = row['metadata']
            rid = meta['record_id']
            tokens = tokenize_payload(row['payload'], tokenizer, contract['token_limits'])
            tokenized.append(dict(record_id=rid, **tokens))
            metas.append({**meta, 'row_index': index, 'training_payload_sha256': digest(row['payload']),
                          'protocol': 'W5_INHERITED_FROZEN_SFT' if rid.startswith('W5_') else 'W6_EVIDENCE_ID_QA_OR_ACTION_HINT'})
            checks.append(dict(record_id=rid, split=split, sequence_tokens=tokens['sequence_tokens']))
        rows_file(split + '.jsonl', [row['payload'] for row in rows])
        rows_file(split + '.metadata.jsonl', metas)
        rows_file('tokenized-' + split + '.jsonl', tokenized)
        stats[split] = dict(count=len(rows), tasks=dict(Counter(m['task_type'] for m in metas)),
                            courses=dict(Counter(m['course_code'] for m in metas)))
    rows_file('addition-candidates.jsonl', candidates)
    write_json(args.output / 'audit.json', dict(status='TECHNICAL_GROUP_CANDIDATE_PENDING_MEMBER_PEER_REVIEW',
        record_count=1000, inherited_records=500, new_a=250, new_b=250, stats=stats,
        tokenizer_records_checked=len(checks), max_sequence_tokens=max(row['sequence_tokens'] for row in checks),
        source_group_and_family_split='PRESERVED', exact_and_5gram_duplicates='PASSED',
        member_reports=member_reports, training='NOT_RUN_ON_GROUP_1000', human_peer_approval_created=False,
        source_rights='DECLARED_NOT_VERIFIED', training_ready=False, group_release_ready=False,
        format='INHERITED_W5_PAYLOADS_PRESERVED_PLUS_NEW_EVIDENCE_ID_PAYLOADS',
        format_transition='PILOT_160_LOCKED_SEPARATELY_UNIFORM_GROUP_CONVERSION_BEFORE_W7_TRAINING'))
    write_json(args.output / 'manifest.json', dict(schema_version='instruction-group-candidate-v1',
        record_count=1000, inputs=dict(old_compact_sha256=sha_file(args.old_compact),
            member_a_manifest_sha256=sha_file(args.member_a / 'manifest.json'),
            member_b_manifest_sha256=sha_file(args.member_b / 'manifest.json')),
        files=inventory(args.output), group_release_ready=False, public_redistribution_allowed=False))
    verify_inventory(args.output, read_json(args.output / 'manifest.json')['files'])
    archive = args.output.with_name(args.output.name + '.zip')
    require(not archive.exists(), 'ARCHIVE_ALREADY_EXISTS')
    with ZipFile(archive, 'x', compression=ZIP_DEFLATED) as zipped:
        for path in sorted(args.output.iterdir()):
            if path.is_file():
                zipped.write(path, path.name)
    write_json(archive.with_name(archive.stem + '-receipt.json'), dict(file=archive.name, sha256=sha_file(archive),
        size_bytes=archive.stat().st_size, manifest_sha256=sha_file(args.output / 'manifest.json'),
        record_count=1000, group_release_ready=False, public_redistribution_allowed=False))
    print('GROUP_1000_TECHNICAL_CANDIDATE', {s:len(rows) for s, rows in splits.items()})


if __name__ == '__main__':
    main()
