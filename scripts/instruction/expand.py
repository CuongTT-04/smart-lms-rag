"""Compile authored additions against locked allocation, PDFs, old data and benchmarks."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from importlib.metadata import version
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from zipfile import ZIP_DEFLATED, ZipFile

from scripts.qlora.data import digest, read_json, read_rows, require, sha_file, tokenize_payload, within
from scripts.qlora.collator import CompletionCollator
from scripts.qlora.runtime import inventory, verify_inventory, write_json


ROOT = Path(__file__).resolve().parents[2]
SPLITS = ('train', 'validation', 'instruction_holdout')


def addition_schema(original):
    schema = deepcopy(original)
    def extend(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == 'pattern' and isinstance(item, str) and item.startswith('^W5_'):
                    value[key] = '^W6_' + item[len('^W5_'):]
                else:
                    extend(item)
        elif isinstance(value, list):
            for item in value:
                extend(item)
    extend(schema)
    schema['$id'] = 'urn:ohayo:instruction-additions:record:v1'
    schema['title'] = 'Instruction additions compatible with the original candidate fields'
    schema['$comment'] = 'Only the real-record ID namespace is extended to locked W6 slots. Original schema and records are unchanged; no approval is granted.'
    return schema


def compact(text):
    return ''.join(unicodedata.normalize('NFC', text).split())


def excerpt(page, start, end):
    require(bool(compact(start)) and bool(compact(end)), 'EMPTY_SOURCE_ANCHOR')
    text = ' '.join(unicodedata.normalize('NFC', page).split())
    positions = [i for i, char in enumerate(text) if not char.isspace()]
    joined = ''.join(text[i] for i in positions)
    require(joined.count(compact(start)) == 1, 'SOURCE_START_NOT_UNIQUE:' + start)
    begin = joined.index(compact(start))
    stop = joined.index(compact(end), begin) + len(compact(end))
    return text[positions[begin]:positions[stop - 1] + 1]


def check_slots(records, slots):
    expected = {s['record_id']: s for s in slots if s['owner_member'] == 'A'}
    require(len(expected) == 250 and len(records) == 250, 'MEMBER_QUOTA')
    require(len({r['record_id'] for r in records}) == 250
            and {r['record_id'] for r in records} == set(expected), 'SLOT_IDS')
    for row in records:
        slot = expected[row['record_id']]
        require(row['author_member'] == 'A' and row['task_type'] == slot['task_type']
                and row['course_code'] == slot['course_code']
                and row['source_group_ids'] == [slot['source_group_id']], 'SLOT_BINDING')
        for ctx in row['contexts']:
            require(int(slot['page_start']) <= ctx['page_number'] <= int(slot['page_end'])
                    and ctx['source_checksum'] == slot['source_checksum'], 'SLOT_PAGE_OR_CHECKSUM')
    require(dict(Counter(r['task_type'] for r in records)) == dict(qa=150, summary=50, hint=25, insufficient_evidence=25), 'TASK_QUOTA')
    require(dict(Counter(r['course_code'] for r in records)) == dict(THMLN=100, KTCTMLN=75, CNXHKH=75), 'COURSE_QUOTA')


def scan_duplicates(records, old_records, exclusion):
    from scripts.w5.common import normalize, similarity
    from scripts.w5.quality import benchmark_inputs
    protected, benchmark_questions, ids, protected_targets, benchmark_targets = benchmark_inputs({'exclusion': exclusion}, ROOT)
    problems = []
    old_questions = {normalize(r['question']): r['record_id'] for r in old_records}
    seen = {}
    def answer(text):
        return normalize(re.sub(r'\[[0-9]+\]', '', text))
    previous = [(r['record_id'], r['question'], answer(r['target_text'])) for r in old_records]
    diagnostics = []
    for row in records:
        rid, q, target = row['record_id'], normalize(row['question']), answer(row['target_text'])
        if q in seen or q in old_questions or hashlib.sha256(q.encode()).hexdigest() in protected or rid in ids:
            problems.append(dict(record_id=rid, code='EXACT_QUESTION_REUSE', other=seen.get(q, old_questions.get(q))))
        seen[q] = rid
        for prior in benchmark_questions:
            if similarity(q, prior) >= 0.85:
                problems.append(dict(record_id=rid, code='BENCHMARK_NEAR', question=prior))
        for prior in benchmark_targets:
            if len(target) >= 80 and similarity(target, prior) >= 0.85:
                problems.append(dict(record_id=rid, code='BENCHMARK_TARGET_NEAR', target=prior))
        if len(target) >= 80 and hashlib.sha256(target.encode()).hexdigest() in protected_targets:
            problems.append(dict(record_id=rid, code='BENCHMARK_TARGET_EXACT'))
        best = (0.0, '', '')
        for old_id, old_q, old_a in previous:
            score = similarity(q, old_q)
            if score > best[0]:
                best = (score, old_id, old_q)
            if score >= 0.85:
                problems.append(dict(record_id=rid, code='OLD_QUESTION_NEAR', other=old_id, question=old_q))
            if min(len(target), len(old_a)) >= 80 and similarity(target, old_a) >= 0.85:
                problems.append(dict(record_id=rid, code='OLD_TARGET_NEAR', other=old_id, target=old_a))
        diagnostics.append(dict(record_id=rid, closest_old_id=best[1], question_similarity=best[0],
                                new_question=row['question'], closest_old_question=best[2]))
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            if similarity(left['question'], right['question']) >= 0.85:
                problems.append(dict(record_id=left['record_id'], code='NEW_QUESTION_NEAR', other=right['record_id']))
            a, b = answer(left['target_text']), answer(right['target_text'])
            if min(len(a), len(b)) >= 80 and similarity(a, b) >= 0.85:
                problems.append(dict(record_id=left['record_id'], code='NEW_TARGET_NEAR', other=right['record_id']))
    return problems, diagnostics


def load_tokenizer(handoff, contract):
    from transformers import AutoTokenizer
    reference = read_json(handoff / 'data/pilot-v2/tokenizer-reference.json')
    for name, expected in reference['packages'].items():
        require(version(name) == expected, 'TOKENIZER_LIBRARY_VERSION:' + name)
    for name, info in reference['files'].items():
        path = within(handoff / 'tokenizer', name)
        require(path.stat().st_size == info['size_bytes'] and sha_file(path) == info['sha256'], 'TOKENIZER_ASSET:' + name)
    tokenizer = AutoTokenizer.from_pretrained(handoff / 'tokenizer', local_files_only=True, trust_remote_code=False)
    require(tokenizer.eos_token_id == contract['model']['eos_token_id']
            and tokenizer.pad_token_id == contract['model']['pad_token_id']
            and hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()
            == contract['model']['chat_template_sha256'], 'TOKENIZER_IDENTITY')
    return tokenizer


def source_split_map(metadata):
    result = {}
    for row in metadata:
        record = row.get('record', row)
        for group in record['source_group_ids']:
            require(group not in result or result[group] == row['split'], 'OLD_SOURCE_SPLIT')
            result[group] = row['split']
    return result


def audit_package(folder, tokenizer, contract, slots, old_metadata, expected_records=None, expected_payloads=None):
    from scripts.w5.common import content_hash
    from jsonschema import Draft202012Validator, FormatChecker
    manifest = read_json(folder / 'manifest.json')
    verify_inventory(folder, manifest['files'])
    require({p.name for p in folder.iterdir() if p.is_file()} == set(manifest['files']) | {'manifest.json'}, 'PACKAGE_FILE_SET')
    records = read_rows(folder / 'candidates.jsonl')
    check_slots(records, slots)
    if expected_records is not None:
        require(records == expected_records, 'AUTHORED_RECORD_RECOMPUTATION')
    by_id = {r['record_id']: r for r in records}
    schema = addition_schema(read_json(ROOT / 'data/instruction/record-schema.json'))
    require(read_json(folder / 'record-schema.json') == schema, 'DERIVED_SCHEMA')
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for row in records:
        validator.validate(row)
        require(content_hash(row) == row['content_sha256'], 'CONTENT_HASH')
    reviews = read_rows(folder / 'self-review.jsonl')
    require(len(reviews) == 250 and len({r['record_id'] for r in reviews}) == 250, 'REVIEW_COUNT')
    for row in reviews:
        require(row['record_id'] in by_id and row['content_sha256'] == by_id[row['record_id']]['content_sha256']
                and row['reviewer_member'] == 'A' and row['peer_approval'] is False
                and row['decision'] == 'ACCEPT_FOR_PRIVATE_INTERNAL_RESEARCH', 'REVIEW_BINDING')
    old_splits = source_split_map(old_metadata)
    allocated = {s['record_id']: s for s in slots}
    collator = CompletionCollator(tokenizer.pad_token_id, tokenizer.eos_token_id, contract['token_limits']['max_sequence_tokens'])
    seen, all_metadata, counts, stats = set(), [], {}, []
    for split in SPLITS:
        payloads = read_rows(folder / (split + '.jsonl'))
        metadata = read_rows(folder / (split + '.metadata.jsonl'))
        tokenized = read_rows(folder / ('tokenized-' + split + '.jsonl'))
        require(len(payloads) == len(metadata) == len(tokenized), 'EXPORTED_ROW_COUNT')
        counts[split] = len(payloads)
        for i, (payload, meta, tokens) in enumerate(zip(payloads, metadata, tokenized)):
            rid = meta['record_id']
            require(rid not in seen and rid in by_id and tokens['record_id'] == meta['source_record_id'] == rid, 'ROW_BINDING')
            seen.add(rid)
            record = by_id[rid]
            require(meta['content_sha256'] == record['content_sha256'] and meta['row_index'] == i
                    and meta['source_group_ids'] == record['source_group_ids']
                    and meta['split'] == allocated[rid]['split'] == old_splits[record['source_group_ids'][0]] == split,
                    'SOURCE_SPLIT_BINDING')
            require(set(payload) == {'prompt','completion'} and len(payload['completion']) == 1
                    and payload['completion'][0]['role'] == 'assistant', 'SFT_PUBLIC_FIELDS')
            if expected_payloads is not None:
                require(payload == expected_payloads[rid], 'AUTHORED_PAYLOAD_RECOMPUTATION')
            require(digest(payload) == meta['sft_sha256'] == meta['training_payload_sha256'], 'PAYLOAD_HASH')
            expected = tokenize_payload(payload, tokenizer, contract['token_limits'])
            require(tokens == dict(record_id=rid, **expected), 'TOKEN_MASK_RECOMPUTATION')
            stats.append(dict(record_id=rid, split=split, **{k:v for k,v in expected.items() if k not in ('input_ids','labels','attention_mask')}))
        for start in range(0, len(tokenized), 4):
            batch = collator.pad([{k:r[k] for k in ('input_ids','attention_mask','labels')} for r in tokenized[start:start + 4]])
            require(all(label == -100 for mask, labels in zip(batch['attention_mask'], batch['labels'])
                        for visible, label in zip(mask, labels) if not visible), 'PAD_MASK')
        all_metadata.extend(metadata)
    require(seen == set(by_id) and counts == dict(train=199, validation=18, instruction_holdout=33), 'SPLIT_COUNTS')
    require(read_rows(folder / 'metadata.jsonl') == all_metadata, 'COMBINED_METADATA')
    report = read_json(folder / 'tokenization-report.json')
    require(report['records'] == stats and report['passed'] is True and report['silent_truncation'] is False, 'TOKEN_REPORT')
    require(read_json(folder / 'findings.json') == [], 'UNRESOLVED_FINDINGS')
    return dict(status='READBACK_AUDIT_PASSED', record_count=len(seen), split_counts=counts,
                tokenizer='PINNED_REAL_QWEN_CPU', retokenized_records=len(seen), collator_batch_size=4,
                prompt_and_padding_masked=True, single_completion_eos=True, silent_truncation=False,
                peer_approval=False, training='NOT_RUN')


def build(specification, allocation, catalog, old_records, created_at):
    from jsonschema import Draft202012Validator, FormatChecker
    from pypdf import PdfReader
    from scripts.w5.common import content_hash
    sys.path.insert(0, str(ROOT / 'backend'))
    from apps.ai.rag.base import EvidenceContext
    from apps.ai.rag.context_builder import build_messages
    from apps.ai.rag.conversation import FORMAT_REPAIR_INSTRUCTION, build_evidence_units, render_structured_answer
    from apps.ai.rag.guardrails import parse_reading_hint
    validator = Draft202012Validator(addition_schema(read_json(ROOT / 'data/instruction/record-schema.json')), format_checker=FormatChecker())
    by_group = {s['source_group_id']: s for s in catalog['sources']}
    slot_map = defaultdict(list)
    for slot in allocation:
        if slot['owner_member'] == 'A':
            slot_map[(slot['source_group_id'], slot['task_type'])].append(slot)
    for slots in slot_map.values():
        slots.sort(key=lambda r: r['record_id'])
    pages, pdfs, checked = {}, {}, {}
    contexts = {}
    for key, selection in specification['sources'].items():
        group, page = selection['group'], selection['page']
        source = by_group[group]
        require(type(page) is int and 1 <= page <= source['page_count'], 'SOURCE_PAGE_BOUNDS')
        path = ROOT / source['relative_path']
        if group not in pdfs:
            require(sha_file(path) == source['source_checksum'], 'PDF_HASH:' + group)
            pdfs[group] = PdfReader(path)
            require(len(pdfs[group].pages) == source['page_count'], 'PDF_PAGE_COUNT')
            checked[group] = source['source_checksum']
        if (group, page) not in pages:
            pages[group, page] = pdfs[group].pages[page - 1].extract_text() or ''
        try:
            text = excerpt(pages[group, page], selection['start'], selection['end'])
        except ValueError as error:
            raise ValueError('SOURCE_ANCHOR:' + key + ':' + group + ':' + str(page)) from error
        contexts[key] = dict(source_id='S1', chunk_id='addition-' + hashlib.sha256(text.encode()).hexdigest()[:24],
            text=text, document_id=source['document_id'], version_id=source['version_id'],
            document_title=source['course_code'] + ' / ' + source['source_doc'], page_number=page,
            section_title=None, source_checksum=source['source_checksum'],
            text_sha256=hashlib.sha256(text.encode()).hexdigest(), rights_reference=source['rights_evidence_reference'])
    records, payloads, reviews = [], {}, []
    for item in specification['items']:
        selections = [specification['sources'][key] for key in item['sources']]
        groups = sorted({s['group'] for s in selections})
        require(len(groups) == 1, 'CROSS_GROUP_SAMPLE_FORBIDDEN')
        slots = slot_map[(groups[0], item['task'])]
        require(bool(slots), 'NO_ALLOCATED_SLOT:' + groups[0] + '/' + item['task'])
        slot = slots.pop(0)
        evidence = [dict(contexts[key], source_id='S' + str(n)) for n, key in enumerate(item['sources'], 1)]
        public_fields = ('source_id', 'chunk_id', 'text', 'document_id', 'version_id', 'document_title', 'page_number', 'section_title')
        prepared = [EvidenceContext.from_value({k: c[k] for k in public_fields}) for c in evidence]
        units = build_evidence_units(prepared)
        require(len(units) == len(evidence), 'ONE_UNIT_PER_EXCERPT_REQUIRED')
        points = item.get('points', [])
        if item['task'] == 'hint':
            legacy = completion = item['action']
            parse_reading_hint(completion, prepared)
            prompt = [dict(m) for m in build_messages(item['question'], 'hint', prepared, None, prompt_version='bounded_guidance')]
            requirements = [item['review_note']]
        else:
            require((item['task'] == 'insufficient_evidence') == (not points), 'TARGET_POINTS')
            mapped = [dict(text=p if isinstance(p, str) else p[1],
                           evidence_id='E' + str(1 if isinstance(p, str) else p[0]) + '.1') for p in points]
            legacy = 'INSUFFICIENT_EVIDENCE' if not points else ' '.join(
                (p if isinstance(p, str) else p[1]).rstrip('.') + ' [' + str(1 if isinstance(p, str) else p[0]) + '].' for p in points)
            completion = json.dumps({'items': mapped}, ensure_ascii=False, separators=(',', ':'))
            render_structured_answer(completion, prepared, require_proof=True)
            prompt = [dict(role='system', content=FORMAT_REPAIR_INSTRUCTION),
                      dict(role='user', content=json.dumps(dict(question=item['question'], mode='qa', evidence=units, exercise=None), ensure_ascii=False))]
            requirements = [p if isinstance(p, str) else p[1] for p in points] or [item['review_note']]
        family = digest({'group': groups[0], 'excerpts': sorted(item['sources'])})[:20]
        record = dict(schema_version='w5-instruction-v1', record_id=slot['record_id'], author_member='A',
            course_code=slot['course_code'], language='vi', task_type=item['task'],
            mode='hint' if item['task'] == 'hint' else 'qa', question=item['question'], contexts=evidence,
            exercise=None, target_text=legacy, source_group_ids=groups, variant_family_id='ADDITION_' + family,
            parent_record_id=None, provenance=dict(method='manual', drafting_tool=None, generation_model_id=None,
                generation_model_revision=None, generation_prompt_sha256=None, recipe_id='page-grounded-additions', created_at=created_at),
            prompt_version='bounded_guidance', source_identity_scope='offline_corpus')
        record['content_sha256'] = content_hash(record)
        validator.validate(record)
        payloads[record['record_id']] = dict(prompt=prompt, completion=[dict(role='assistant', content=completion)])
        records.append(record)
        reviews.append(dict(record_id=record['record_id'], content_sha256=record['content_sha256'],
            reviewer_member='A', review_kind='SELF_REVIEW', required_points=requirements,
            source_pages=[{'group': group, 'page': s['page']} for group, s in zip([groups[0]] * len(selections), selections)],
            decision='ACCEPT_FOR_PRIVATE_INTERNAL_RESEARCH', peer_approval=False,
            reason=item.get('review_note', 'Đối chiếu các ý bắt buộc với đoạn nguồn; giữ đủ từng vế, citation và giới hạn phát biểu.'),
            reviewed_at=created_at))
    return sorted(records, key=lambda r: r['record_id']), payloads, reviews, checked, len(pages)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--handoff', type=Path, required=True)
    parser.add_argument('--old-package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args(argv)
    require(args.audit_only or not args.output.exists(), 'OUTPUT_EXISTS')
    require(args.output.resolve().is_relative_to(ROOT / '.private'), 'PRIVATE_OUTPUT_REQUIRED')
    source_root = args.handoff / 'source'
    allocation_file = source_root / 'data/w6/record-allocation.csv'
    allocation_report = read_json(source_root / 'data/w6/source-allocation.json')
    package_manifest = read_json(args.handoff / 'package-manifest.json')
    require(sha_file(allocation_file) == package_manifest['files']['source/data/w6/record-allocation.csv']['sha256'],
            'LOCKED_ALLOCATION_FILE_HASH')
    with allocation_file.open(encoding='utf-8-sig', newline='') as stream:
        slots = list(csv.DictReader(stream))
    typed_slots = [dict(s, page_start=int(s['page_start']), page_end=int(s['page_end']),
                        public_redistribution_allowed=s['public_redistribution_allowed'] == 'True') for s in slots]
    require(digest(typed_slots) == allocation_report['allocation_sha256'], 'LOCKED_ALLOCATION_CANONICAL_HASH')
    contract = read_json(args.handoff / 'data/pilot-v2/training-contract.json')
    catalog_file = source_root / contract['source_manifest']['path']
    require(sha_file(catalog_file) == contract['source_manifest']['sha256'], 'SOURCE_REGISTRY_HASH')
    original_manifest = read_json(args.old_package / 'manifest.json')
    verify_inventory(args.old_package, original_manifest['files'])
    old_records = read_rows(args.old_package / 'candidates.jsonl')
    require(len(old_records) == 500, 'OLD_500_REQUIRED')
    specification = read_json(args.spec)
    created = datetime.now(timezone.utc).isoformat()
    if args.audit_only:
        require(not args.inspect, 'EXCLUSIVE_AUDIT_MODE')
        created = read_rows(args.output / 'candidates.jsonl')[0]['provenance']['created_at']
    records, payloads, reviews, checked, page_count = build(specification, slots, read_json(catalog_file), old_records, created)
    if not args.inspect:
        check_slots(records, slots)
    else:
        print('Counts:', len(records), dict(Counter(r['course_code'] for r in records)), dict(Counter(r['task_type'] for r in records)))
    problems, diagnostics = scan_duplicates(records, old_records, read_json(ROOT / 'data/instruction/w5/contract/benchmark-exclusion-manifest.json'))
    if args.audit_only:
        require(not problems, 'DUPLICATE_RECHECK')
        report = audit_package(args.output, load_tokenizer(args.handoff, contract), contract, slots,
                               read_rows(args.old_package / 'metadata.jsonl'), records, payloads)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    args.output.mkdir(parents=True)
    write_json(args.output / 'findings.json', problems)
    if problems or args.inspect:
        write_json(args.output / 'novelty.json', diagnostics)
        print(json.dumps(problems, ensure_ascii=False, indent=2))
        print('INSPECT_ONLY_NOT_RELEASED' if args.inspect else 'BLOCKED_DUPLICATE_REVIEW')
        return 0 if args.inspect else 1
    tokenizer = load_tokenizer(args.handoff, contract)
    maximum = 0
    old_meta = read_rows(args.old_package / 'metadata.jsonl')
    old_splits = source_split_map(old_meta)
    allocations = {s['record_id']: s for s in slots}
    metadata, token_stats, split_counts = [], [], {}
    def save_rows(name, values):
        (args.output / name).write_text(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False) + '\n' for r in values), encoding='utf-8')
    for split in SPLITS:
        rows = [r for r in records if allocations[r['record_id']]['split'] == split]
        split_counts[split] = len(rows)
        tokenized, sidecar = [], []
        for index, row in enumerate(rows):
            group = row['source_group_ids'][0]
            require(old_splits[group] == split, 'OLD_NEW_SOURCE_SPLIT_LEAKAGE')
            payload = payloads[row['record_id']]
            try:
                tokens = tokenize_payload(payload, tokenizer, contract['token_limits'])
            except ValueError as error:
                raise ValueError('TOKENIZATION:' + row['record_id']) from error
            maximum = max(maximum, tokens['sequence_tokens'])
            tokenized.append(dict(record_id=row['record_id'], **tokens))
            token_stats.append(dict(record_id=row['record_id'], split=split, **{k:v for k,v in tokens.items() if k not in ('input_ids','labels','attention_mask')}))
            sidecar.append(dict(record_id=row['record_id'], source_record_id=row['record_id'],
                content_sha256=row['content_sha256'], split=split, row_index=index,
                author_member='A', course_code=row['course_code'], task_type=row['task_type'],
                source_group_ids=row['source_group_ids'], variant_family_id=row['variant_family_id'],
                source_identity_scope='offline_corpus', sft_sha256=digest(payload), training_payload_sha256=digest(payload),
                sources=[{k:c[k] for k in ('source_id','document_id','version_id','page_number','source_checksum','text_sha256','rights_reference')} for c in row['contexts']],
                self_review='ACCEPTED_INTERNAL_RESEARCH', peer_review='NOT_ASSERTED'))
        save_rows(split + '.jsonl', [payloads[r['record_id']] for r in rows])
        save_rows(split + '.metadata.jsonl', sidecar)
        save_rows('tokenized-' + split + '.jsonl', tokenized)
        metadata.extend(sidecar)
    save_rows('candidates.jsonl', records)
    save_rows('metadata.jsonl', metadata)
    save_rows('self-review.jsonl', sorted(reviews, key=lambda r: r['record_id']))
    write_json(args.output / 'record-schema.json', addition_schema(read_json(ROOT / 'data/instruction/record-schema.json')))
    write_json(args.output / 'authored-specs.json', specification)
    write_json(args.output / 'novelty.json', diagnostics)
    write_json(args.output / 'tokenization-report.json', dict(passed=True, records=token_stats,
        max_sequence_tokens=maximum, limits=contract['token_limits'], silent_truncation=False,
        loss_scope='COMPLETION_AND_SINGLE_EOS_ONLY', holdout_is_separate=True))
    write_json(args.output / 'dataset-config.json', dict(record_count=250, author_member='A',
        course_counts=dict(Counter(r['course_code'] for r in records)), task_counts=dict(Counter(r['task_type'] for r in records)),
        split_counts=split_counts, model=contract['model'], protocol='evidence_citations_v2',
        token_limits=contract['token_limits'], training='NOT_RUN', peer_approval=False,
        public_redistribution_allowed=False, source_rights='DECLARED_NOT_VERIFIED',
        scope='PRIVATE_INTERNAL_RESEARCH_MEMBER_ADDITIONS_NOT_GROUP_1000_RELEASE'))
    write_json(args.output / 'audit.json', dict(status='MEMBER_ADDITIONS_SELF_REVIEWED_AND_TECHNICALLY_AUDITED',
        record_count=250, split_counts=split_counts, sources_verified=checked, pages_verified=page_count,
        exact_and_5gram_duplicate_scan='PASSED_AGAINST_NEW_250_OLD_500_AND_PROTECTED_BENCHMARKS',
        semantic_novelty='AUTHORED_FROM_NEW_SOURCE_SELECTIONS_AND_OWNER_REVIEW_NOT_EXHAUSTIVE_PROOF',
        self_reviewed_records=250, peer_approved_records=0, model_calls=0, gpu_used=False,
        old_dataset_unchanged=True, locked_allocation_unchanged=True, training='NOT_RUN'))
    write_json(args.output / 'manifest.json', dict(record_count=250, split_counts=split_counts,
        inputs=dict(allocation_sha256=sha_file(allocation_file), source_manifest_sha256=sha_file(catalog_file),
            old_manifest_sha256=sha_file(args.old_package / 'manifest.json'), authored_spec_sha256=sha_file(args.spec)),
        tool_sha256=sha_file(__file__), files=inventory(args.output)))
    readback = audit_package(args.output, tokenizer, contract, slots, old_meta, records, payloads)
    write_json(args.output.with_name('readback-audit.json'), readback)
    archive = args.output.with_name('instruction-additions.zip')
    require(not archive.exists(), 'ARCHIVE_EXISTS')
    with ZipFile(archive, 'x', compression=ZIP_DEFLATED) as zipped:
        for path in sorted(args.output.iterdir()):
            if path.is_file():
                zipped.write(path, path.name)
    with ZipFile(archive) as zipped:
        require(zipped.testzip() is None and set(zipped.namelist()) == {p.name for p in args.output.iterdir() if p.is_file()}, 'ZIP_CRC_OR_FILE_SET')
        for name in zipped.namelist():
            require(hashlib.sha256(zipped.read(name)).hexdigest() == sha_file(args.output / name), 'ZIP_ENTRY_HASH')
    write_json(args.output.with_name('instruction-additions-receipt.json'), dict(file=archive.name,
        sha256=sha_file(archive), size_bytes=archive.stat().st_size,
        manifest_sha256=sha_file(args.output / 'manifest.json'), record_count=250,
        peer_approval=False, public_redistribution_allowed=False))
    print('MEMBER_ADDITIONS_READY:', split_counts, 'max_sequence_tokens=', maximum)
    return 0


if __name__ == '__main__':
    sys.exit(main())
