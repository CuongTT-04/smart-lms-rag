"""Normalize the authenticated instruction source without moving records across splits."""
import argparse
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import unicodedata
from zipfile import ZipFile

from scripts.qlora.data import digest, read_json, require, sha_file, tokenize_payload
from scripts.qlora.collator import CompletionCollator
from scripts.qlora.runtime import inventory, verify_inventory, write_json
from scripts.w6.prepare_pilot import convert_row
from scripts.w6.contracts import load_archive, SourceVerifier

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SHA = '8bcc3af65024f2d90d8a921da58dbc8f31909c52b66da943d1e4c488fb6f0036'
COUNTS = {'train': 385, 'validation': 57, 'instruction_holdout': 58}


def compact(text):
    return ''.join(unicodedata.normalize('NFC', text).split())


def source_repairs(payload, metadata, pages):
    """Explicit reviewed corrections; ambiguous multi-page claims never use fuzzy attribution."""
    row, meta = deepcopy(payload), deepcopy(metadata)
    rid = meta['record_id']
    user = json.loads(row['prompt'][-1]['content'])
    target = row['completion'][0]['content']
    changes = []
    if rid == 'W5_A_00139':
        # The original condition/conclusion straddles pages 26/27. The formula
        # on physical page 26 supports p=0 without inventing a cross-page ID.
        page = ' '.join(pages['KTCTMLN:ch03.pdf', 26].split())
        start = page.index('Trong thực tế sản xuất kinh doanh')
        end = page.index('Từ đó p = G - k.') + len('Từ đó p = G - k.')
        user['evidence'][0]['text'] = page[start:end]
        meta['sources'][0]['text_sha256'] = hashlib.sha256(user['evidence'][0]['text'].encode()).hexdigest()
        require(target == 'Khi bán đúng bằng chi phí sản xuất thì không có lợi nhuận [1] [2].', 'REPAIR_SOURCE_CHANGED')
        row['completion'][0]['content'] = target.replace('[1] [2]', '[1]')
        changes.append('Extend source 1 using the exact same-page formula p=G-k; G=k implies p=0. Replace the ambiguous two-page citation with the reviewed formula source.')
    elif rid == 'W5_A_00146':
        require('[2] [3]' in target and 'p = G - k' in user['evidence'][0]['text'], 'REPAIR_SOURCE_CHANGED')
        row['completion'][0]['content'] = target.replace('[2] [3]', '[1]')
        changes.append('The no-profit clause is supported by the already supplied p=G-k formula in source 1; retain the other claims and their original sources.')
    elif rid == 'W5_B_00008':
        lines = [re.sub(r'^-\s*', '', line).strip() for line in target.splitlines() if line.strip()]
        require(len(lines) == 3 and len(user['evidence']) == 1, 'REPAIR_SOURCE_CHANGED')
        row['completion'][0]['content'] = ' '.join(re.sub(r'\s*\[1\]', '', line).rstrip(' .') + ' [1].' for line in lines)
        changes.append('Split the three existing bullet claims into individually cited items, each bound to the same supplied paragraph; do not add answer content.')
    if changes:
        row['prompt'][-1]['content'] = json.dumps(user, ensure_ascii=False)
        # Preserve the original payload identity separately from conversion input.
        meta['sft_sha256'] = digest(row)
    return row, meta, changes


def prepare(archive, handoff, corpus, output, group_archive=None):
    archive, handoff, corpus, output = map(Path, (archive, handoff, corpus, output))
    require(not output.exists() and output.resolve().is_relative_to(ROOT / '.private'), 'NEW_PRIVATE_OUTPUT_REQUIRED')
    contract = read_json(handoff / 'data/pilot-v2/training-contract.json')
    require(sha_file(archive) == EXPECTED_SHA, 'SOURCE_ARCHIVE_PIN')
    source = load_archive(archive, contract['expected_compact'])
    require(Counter(row['metadata']['split'] for row in source['records']) == COUNTS, 'SOURCE_SPLITS')
    counts = COUNTS
    if group_archive is not None:
        from scripts.comparison.instruction_source import GROUP_COUNTS, load_group
        with (handoff / 'source/data/w6/record-allocation.csv').open(encoding='utf-8-sig', newline='') as handle:
            allocation = list(csv.DictReader(handle))
        source = load_group(group_archive, source, allocation)
        counts = GROUP_COUNTS
    total = sum(counts.values())
    registry = read_json(corpus / 'source-manifest.json')
    verifier = SourceVerifier(registry, corpus)
    verifier.check_registry()
    for row in source['records']:
        verifier.check(dict(payload=row.get('source_payload', row['payload']), metadata=row['metadata']))
    from transformers import AutoTokenizer
    token_ref = read_json(handoff / 'data/pilot-v2/tokenizer-reference.json')
    for name, info in token_ref['files'].items():
        path = handoff / 'tokenizer' / name
        require(sha_file(path) == info['sha256'] and path.stat().st_size == info['size_bytes'], 'TOKENIZER_BYTES')
    tokenizer = AutoTokenizer.from_pretrained(handoff / 'tokenizer', local_files_only=True, trust_remote_code=False)
    require(hashlib.sha256(tokenizer.chat_template.encode()).hexdigest() == token_ref['chat_template_sha256'], 'TOKENIZER_TEMPLATE')
    limits = contract['token_limits']
    collator = CompletionCollator(tokenizer.pad_token_id, tokenizer.eos_token_id, limits['max_sequence_tokens'])
    staged, corrections = {}, []
    for row in source['records']:
        old, old_meta = row['payload'], row['metadata']
        if 'incoming_tokens' in row:
            require(row['incoming_tokens'] == dict(record_id=old_meta['record_id'], **tokenize_payload(old, tokenizer, limits)), 'GROUP_INCOMING_TOKEN_MASK')
        if 'source_payload' in row:
            modified, meta, changes = deepcopy(old), deepcopy(old_meta), []
            meta.update(source_record_id=old_meta['record_id'], source_content_sha256=old_meta['content_sha256'],
                        source_row_index=old_meta['row_index'], semantic_peer_review='NOT_ASSERTED')
            converted = dict(payload=modified, metadata=meta, mapping=row['native_mapping'])
        else:
            modified, meta, changes = source_repairs(old, old_meta, verifier.cache)
            if changes:
                verifier.check({'payload': modified, 'metadata': meta})
            converted = convert_row(modified, meta)
        metadata = converted['metadata']
        metadata.update(record_id=old_meta['record_id'], source_sft_sha256=old_meta['sft_sha256'],
                        conversion_input_sha256=digest(modified), original_target_preserved_except_protocol=not changes,
                        source_repair=bool(changes), conversion_version='explicit-evidence-expanded-v1',
                        inherited_protocol='NATIVE_EVIDENCE_ID' if 'source_payload' in row else 'LEGACY_INLINE_CITATION')
        tokens = tokenize_payload(converted['payload'], tokenizer, limits)
        staged.setdefault(old_meta['split'], []).append({'payload': converted['payload'], 'metadata': metadata,
            'tokens': dict(record_id=old_meta['record_id'], **tokens), 'mapping': converted['mapping']})
        if changes:
            corrections.append({'record_id': old_meta['record_id'], 'split': old_meta['split'],
                'old_payload_sha256': digest(old), 'new_payload_sha256': digest(converted['payload']),
                'changes': changes, 'old_target': old['completion'][0]['content'],
                'new_target': converted['payload']['completion'][0]['content'], 'review': 'SOURCE_CHECKED_CORRECTION'})
    require({s: len(rr) for s, rr in staged.items()} == counts, 'NORMALIZED_COUNTS')
    output.mkdir(parents=True)
    def save_rows(name, values):
        (output / name).write_text(''.join(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n' for value in values), encoding='utf-8')
    metadata, mapping, stats = [], [], []
    for split in counts:
        values = staged[split]
        for index, row in enumerate(values):
            row['metadata']['row_index'] = index
        for index in range(0, len(values), 4):
            collator.pad([{k: row['tokens'][k] for k in ('input_ids', 'attention_mask', 'labels')} for row in values[index:index+4]])
        save_rows(split + '.jsonl', [row['payload'] for row in values])
        save_rows(split + '.metadata.jsonl', [row['metadata'] for row in values])
        save_rows('tokenized-' + split + '.jsonl', [row['tokens'] for row in values])
        metadata.extend(row['metadata'] for row in values)
        mapping.extend({'record_id': row['metadata']['record_id'], 'split': split, 'assignments': row['mapping']} for row in values)
        stats.extend(dict(record_id=row['metadata']['record_id'], split=split,
            **{k: v for k, v in row['tokens'].items() if k not in ('record_id', 'input_ids', 'labels', 'attention_mask')}) for row in values)
    save_rows('metadata.jsonl', metadata)
    save_rows('mapping.jsonl', mapping)
    write_json(output / 'corrections.json', corrections)
    write_json(output / 'tokenizer-reference.json', token_ref)
    write_json(output / 'dataset-config.json', dict(record_count=total, split_counts=counts, token_limits=limits,
        model=contract['model'], source_archive_sha256=source['archive_sha256'], original_compact_sha256=EXPECTED_SHA,
        epochs=1, effective_batch_size=4,
        estimated_updates=math.ceil(counts['train']/4), training='NOT_RUN', semantic_review='INHERITED_CONTENT_WITH_THREE_SOURCE_CHECKED_CORRECTIONS',
        holdout_for_training=False, public_redistribution_allowed=False))
    write_json(output / 'tokenization-report.json', dict(records_checked=total, records=stats,
        max_sequence_tokens=max(row['sequence_tokens'] for row in stats), prompt_and_padding_masked=True,
        single_supervised_eos=True, silent_truncation=False, model_weights_loaded=False, gpu_used=False))
    write_json(output / 'manifest.json', dict(schema_version='comparison-training-data-v1', record_count=total,
        split_counts=counts, source_archive_sha256=source['archive_sha256'], original_compact_sha256=EXPECTED_SHA,
        tools_sha256=sha_file(__file__),
        source_loader_sha256=sha_file(Path(__file__).with_name('instruction_source.py')) if group_archive else None,
        source_pdf_sha256={r['source_group_id']: r['source_checksum'] for r in registry['sources']},
        source_pages_checked=len(verifier.checked), corrections=len(corrections), files=inventory(output),
        technical_normalization='PASSED', benchmark_leakage='PENDING_SEPARATE_AUDIT', training_ready=False))
    return audit(output, handoff)


def audit(folder, handoff):
    folder, handoff = Path(folder), Path(handoff)
    manifest = read_json(folder / 'manifest.json')
    counts = manifest['split_counts']
    from scripts.comparison.instruction_source import GROUP_COUNTS
    require(counts in (COUNTS, GROUP_COUNTS) and manifest['record_count'] == sum(counts.values()), 'AUDIT_SPLIT_POLICY')
    verify_inventory(folder, manifest['files'])
    require(set(inventory(folder, ('manifest.json',))) == set(manifest['files']), 'PACKAGE_FILE_SET')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(handoff / 'tokenizer', local_files_only=True, trust_remote_code=False)
    limits = read_json(folder / 'dataset-config.json')['token_limits']
    seen, groups, families = set(), {}, {}
    from scripts.qlora.data import read_rows
    for split, count in counts.items():
        payloads = read_rows(folder / (split + '.jsonl'))
        metas = read_rows(folder / (split + '.metadata.jsonl'))
        tokens = read_rows(folder / ('tokenized-' + split + '.jsonl'))
        require(len(payloads) == len(metas) == len(tokens) == count, 'AUDIT_COUNTS')
        for index, (p, m, t) in enumerate(zip(payloads, metas, tokens)):
            rid = m['record_id']
            require(rid not in seen and m['source_record_id'] == rid and m['split'] == split and m['row_index'] == index, 'AUDIT_ID_SPLIT')
            seen.add(rid)
            require(m['training_payload_sha256'] == digest(p), 'AUDIT_PAYLOAD_HASH')
            require(t == dict(record_id=rid, **tokenize_payload(p, tokenizer, limits)), 'AUDIT_TOKENS')
            for group in m['source_group_ids']:
                require(group not in groups or groups[group] == split, 'GROUP_SPLIT_LEAKAGE')
                groups[group] = split
            family = m['variant_family_id']
            require(family not in families or families[family] == split, 'FAMILY_SPLIT_LEAKAGE')
            families[family] = split
    return dict(status='NORMALIZED_PACKAGE_READBACK_PASSED', record_count=len(seen), split_counts=counts,
                manifest_sha256=sha_file(folder / 'manifest.json'), training='NOT_RUN',
                max_sequence_tokens=read_json(folder / 'tokenization-report.json')['max_sequence_tokens'],
                corrections=manifest['corrections'], source_pages_checked=manifest['source_pages_checked'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ROOT / '.private/instruction/ohayo-instruction.zip')
    parser.add_argument('--handoff', type=Path, default=ROOT / '.private/qlora/inputs/handoff')
    parser.add_argument('--corpus', type=Path, default=ROOT / '.private/comparison/inputs/v3/evaluator/main')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--group-archive', type=Path, help='Authenticated 1,000-record candidate; keeps the original compact as a lineage anchor')
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args()
    result = audit(args.output, args.handoff) if args.audit_only else prepare(args.archive, args.handoff, args.corpus, args.output, args.group_archive)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
