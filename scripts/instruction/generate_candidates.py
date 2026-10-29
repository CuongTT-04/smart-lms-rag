"""Assign stable IDs and hashes to authored drafts; no inference or auto-approval."""
import argparse
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from filelock import FileLock
from scripts.instruction.common import (atomic_write, canonical, content_hash,
    guard_output, jsonl_bytes, load_resources, question_key, read_jsonl, require, validate_records)


def generate(drafts, output, resources, *, member='A', preview=False, private_draft=False):
    require(member in ('A', 'B'), 'INVALID_MEMBER')
    output = guard_output(output)
    if private_draft:
        private_root = (resources.root/'.private/instruction').resolve()
        require(output.is_relative_to(private_root), 'PRIVATE_DRAFT_OUTPUT_MUST_STAY_PRIVATE')
    output.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(output) + '.lock', timeout=10):
        existing = read_jsonl(output) if output.exists() else []
        if existing:
            validate_records(existing, resources, preview=preview, private_draft=private_draft)
            require(all(row['author_member'] == member for row in existing), 'MIXED_AUTHOR_OUTPUT')
        rows = deepcopy(existing)
        fields = set(resources.schema['required']) - {'record_id', 'content_sha256'}
        by_question = {question_key(row['question']): row for row in rows}
        sequence = max((int(row['record_id'].rsplit('_', 1)[1]) for row in rows), default=0)
        prefix = 'FX_W5' if preview else f'W5_{member}'
        for draft in drafts:
            require(isinstance(draft, dict) and set(draft) == fields, 'INVALID_DRAFT_FIELDS')
            require(draft['author_member'] == member, 'DRAFT_AUTHOR_MISMATCH')
            require(isinstance(draft['question'], str) and bool(draft['question'].strip()), 'INVALID_DRAFT_QUESTION')
            key = question_key(draft['question'])
            if key in by_question:
                old = {k: v for k, v in by_question[key].items() if k in fields}
                require(canonical(old) == canonical(draft), 'EXISTING_DRAFT_CHANGED')
                continue
            sequence += 1
            require(sequence <= 99999, 'ID_RANGE_EXHAUSTED')
            row = {**deepcopy(draft), 'record_id': f'{prefix}_{sequence:05d}'}
            row['content_sha256'] = content_hash(row)
            rows.append(row)
            by_question[key] = row
        validate_records(rows, resources, preview=preview, private_draft=private_draft)
        if rows != existing:
            atomic_write(output, jsonl_bytes(rows))
        return {'record_count': len(rows), 'added_count': len(rows)-len(existing),
                'status': ('PRIVATE_DRAFT_RIGHTS_UNVERIFIED' if private_draft else
                           'FIXTURE_ONLY' if preview else 'DRAFT_NOT_REVIEWED'), 'model_calls': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--drafts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--member', choices=('A','B'), default='A')
    parser.add_argument('--contract', type=Path, default=ROOT/'data/instruction/input-contract.json')
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--preview', action='store_true', help='Only self-authored fixture records; never real candidates.')
    parser.add_argument('--private-draft', action='store_true', help='Private research draft only; no source rights approval or SFT export.')
    args = parser.parse_args(argv)
    try:
        guard_output(args.output, [args.drafts, args.contract, *([args.bundle] if args.bundle else [])])
        result = generate(read_jsonl(args.drafts), args.output,
                          load_resources(args.contract, preview=args.preview, bundle=args.bundle),
                          member=args.member, preview=args.preview, private_draft=args.private_draft)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'{type(error).__name__}: {error}\n')
    print(result)


if __name__ == '__main__':
    main()
