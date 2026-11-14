"""Authenticate the received group archive and bind native rows to authored candidates."""
from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path
import re
import stat
import sys
from zipfile import ZipFile

from scripts.qlora.data import digest, require
from scripts.w6.contracts import jsonl, loads, validate_payload

GROUP_SHA = '7cd57224a56d1f4265535ae27523913933726adeaf85b570e75187ce1e50475b'
GROUP_COUNTS = dict(train=770, validation=114, instruction_holdout=116)
GROUP_FILES = {'manifest.json', 'audit.json', 'addition-candidates.jsonl',
               *(s + '.jsonl' for s in GROUP_COUNTS),
               *(s + '.metadata.jsonl' for s in GROUP_COUNTS),
               *('tokenized-' + s + '.jsonl' for s in GROUP_COUNTS)}


def archive_files(path, expected_sha=GROUP_SHA):
    path = Path(path)
    require(path.stat().st_size <= 32 * 1024 * 1024, 'GROUP_ARCHIVE_SIZE')
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha, 'GROUP_ARCHIVE_PIN')
    with ZipFile(path) as zipped:
        infos = zipped.infolist()
        names = [info.filename for info in infos]
        require(len(names) == len(set(names)) and set(names) == GROUP_FILES, 'GROUP_ARCHIVE_MEMBERS')
        require(all(not i.is_dir() and not stat.S_ISLNK(i.external_attr >> 16)
                    and not i.flag_bits & 1 for i in infos), 'GROUP_ARCHIVE_FILE_TYPE')
        require(sum(i.file_size for i in infos) <= 80 * 1024 * 1024, 'GROUP_EXPANDED_SIZE')
        files = {name: zipped.read(name) for name in names}
    manifest = loads(files['manifest.json'])
    require(set(manifest['files']) == GROUP_FILES - {'manifest.json'}, 'GROUP_MANIFEST_MEMBERS')
    require(manifest['schema_version'] == 'instruction-group-candidate-v1' and manifest['record_count'] == 1000, 'GROUP_MANIFEST_SCHEMA')
    for name, expected in manifest['files'].items():
        raw = files[name]
        require(len(raw) == expected['size_bytes'] and hashlib.sha256(raw).hexdigest() == expected['sha256'], 'GROUP_MEMBER_INTEGRITY:' + name)
    return files, manifest


def candidate_payload(candidate, payload):
    """Reconstruct the source view and check every native claim/citation binding."""
    import json
    backend = str(Path(__file__).resolve().parents[2] / 'backend')
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from apps.ai.rag.base import EvidenceContext
    from apps.ai.rag.context_builder import build_messages
    from apps.ai.rag.conversation import FORMAT_REPAIR_INSTRUCTION, build_evidence_units, render_structured_answer
    from apps.ai.rag.guardrails import check_request_policy, parse_reading_hint
    require(not re.search(r'<\|[^<>\r\n]{1,80}\|>', json.dumps(candidate, ensure_ascii=False)), 'GROUP_SPECIAL_TOKEN_IN_DATA')
    check_request_policy(candidate['question'])
    contexts = []
    public = ('source_id', 'chunk_id', 'text', 'document_id', 'version_id', 'document_title', 'page_number', 'section_title')
    for index, source in enumerate(candidate['contexts'], 1):
        require(source['source_id'] == 'S' + str(index), 'GROUP_SOURCE_ORDER')
        require(hashlib.sha256(source['text'].encode()).hexdigest() == source['text_sha256'], 'GROUP_SOURCE_TEXT_HASH')
        contexts.append(EvidenceContext.from_value({key: source[key] for key in public}))
    user = dict(question=candidate['question'], mode=candidate['mode'],
                evidence=[dict({key: source[key] for key in public}, citation_label=i)
                          for i, source in enumerate(candidate['contexts'], 1)], exercise=candidate['exercise'])
    legacy = dict(prompt=[dict(role='system', content='Source verification view'),
                          dict(role='user', content=json.dumps(user, ensure_ascii=False))],
                  completion=[dict(role='assistant', content=candidate['target_text'])])
    validate_payload(legacy)
    require(candidate['exercise'] is None, 'GROUP_EXERCISE')
    if candidate['task_type'] == 'hint':
        require(candidate['mode'] == 'hint', 'GROUP_TASK_MODE')
        parse_reading_hint(candidate['target_text'], contexts)
        expected = dict(prompt=[dict(m) for m in build_messages(candidate['question'], 'hint', contexts, None, prompt_version='bounded_guidance')],
                        completion=[dict(role='assistant', content=candidate['target_text'])])
        mapping = []
    else:
        require(candidate['mode'] == 'qa', 'GROUP_TASK_MODE')
        require(set(payload) == {'prompt', 'completion'} and len(payload['completion']) == 1, 'GROUP_PAYLOAD_FIELDS')
        raw = payload['completion'][0]['content']
        answer = loads(raw)
        require(set(answer) == {'items'} and isinstance(answer['items'], list), 'GROUP_TARGET_SCHEMA')
        units = build_evidence_units(contexts)
        by_id = {unit['evidence_id']: unit for unit in units}
        require(all(set(item) == {'text', 'evidence_id'} and item['evidence_id'] in by_id
                    and isinstance(item['text'], str) and bool(item['text'].strip()) for item in answer['items']), 'GROUP_CLAIM_BINDING')
        require((candidate['task_type'] == 'insufficient_evidence') == (not answer['items']), 'GROUP_REFUSAL')
        target = ' '.join(item['text'].rstrip('.') + ' [' + str(by_id[item['evidence_id']]['citation_label']) + '].'
                          for item in answer['items']) if answer['items'] else 'INSUFFICIENT_EVIDENCE'
        require(target == candidate['target_text'], 'GROUP_CANDIDATE_TARGET_BINDING')
        render_structured_answer(raw, contexts, require_proof=True)
        expected = dict(prompt=[dict(role='system', content=FORMAT_REPAIR_INSTRUCTION),
                        dict(role='user', content=json.dumps(dict(question=candidate['question'], mode='qa', evidence=units, exercise=None), ensure_ascii=False))],
                        completion=[dict(role='assistant', content=json.dumps(answer, ensure_ascii=False, separators=(',', ':')))])
        mapping = [dict(claim_index=i, evidence_id=item['evidence_id'],
                        source_id=contexts[by_id[item['evidence_id']]['citation_label']-1].source_id,
                        method='AUTHORED_CANDIDATE_EXPLICIT_EVIDENCE_ID') for i, item in enumerate(answer['items'])]
    require(payload == expected, 'GROUP_AUTHORED_PAYLOAD_BINDING')
    return legacy, mapping


def load_group(path, original, allocation):
    from jsonschema import Draft202012Validator, FormatChecker
    from scripts.instruction.expand import addition_schema, check_slots, validate_payload_binding
    from scripts.w5.common import content_hash
    from scripts.qlora.data import read_json
    from scripts.w6.contracts import ROOT
    files, manifest = archive_files(path)
    require(manifest['inputs']['old_compact_sha256'] == original['archive_sha256'], 'GROUP_INHERITED_ARCHIVE_PIN')
    candidates = jsonl(files['addition-candidates.jsonl'])
    require(len(candidates) == 500 and len({r['record_id'] for r in candidates}) == 500, 'GROUP_ADDITION_COUNT')
    validator = Draft202012Validator(addition_schema(read_json(ROOT / 'data/instruction/record-schema.json')), format_checker=FormatChecker())
    for member in ('A', 'B'):
        check_slots([r for r in candidates if r['author_member'] == member], allocation, member=member)
    for row in candidates:
        validator.validate(row)
        require(content_hash(row) == row['content_sha256'], 'GROUP_CANDIDATE_HASH')
    added = {r['record_id']: r for r in candidates}
    inherited = {r['metadata']['record_id']: r for r in original['records']}
    require(not added.keys() & inherited.keys(), 'GROUP_INHERITED_ADDITION_ID_COLLISION')
    records, seen, groups, families = [], set(), {}, {}
    for split, count in GROUP_COUNTS.items():
        payloads = jsonl(files[split + '.jsonl'])
        metadata = jsonl(files[split + '.metadata.jsonl'])
        tokens = jsonl(files['tokenized-' + split + '.jsonl'])
        require(len(payloads) == len(metadata) == len(tokens) == count, 'GROUP_SPLIT_COUNTS')
        for index, (payload, meta, token) in enumerate(zip(payloads, metadata, tokens)):
            rid = meta['record_id']
            require(rid not in seen and rid in inherited.keys() | added.keys(), 'GROUP_RECORD_ID')
            seen.add(rid)
            require(meta['split'] == split and meta['row_index'] == index and token['record_id'] == rid, 'GROUP_ROW_POSITION')
            require(digest(payload) == meta['sft_sha256'] == meta['training_payload_sha256'], 'GROUP_PAYLOAD_HASH')
            require(isinstance(meta['source_group_ids'], list) and bool(meta['source_group_ids']), 'GROUP_SOURCE_REQUIRED')
            for group in meta['source_group_ids']:
                require(group not in groups or groups[group] == split, 'GROUP_SPLIT_LEAKAGE')
                groups[group] = split
            family = meta['variant_family_id']
            require(isinstance(family, str) and bool(family) and (family not in families or families[family] == split), 'GROUP_FAMILY_LEAKAGE')
            families[family] = split
            row = dict(payload=payload, metadata=meta, incoming_tokens=token)
            if rid in inherited:
                old = inherited[rid]
                require(payload == old['payload'], 'GROUP_INHERITED_PAYLOAD_CHANGED')
                require(all(meta.get(k) == v for k, v in old['metadata'].items() if k != 'row_index'), 'GROUP_INHERITED_METADATA_CHANGED')
            else:
                candidate = added[rid]
                require(meta['source_record_id'] == rid, 'GROUP_SOURCE_RECORD_ID')
                require(meta['content_sha256'] == candidate['content_sha256'] and meta['source_group_ids'] == candidate['source_group_ids'], 'GROUP_ADDITION_METADATA')
                require(split == original['source_group_splits'][candidate['source_group_ids'][0]], 'GROUP_ADDITION_SPLIT')
                legacy, mapping = candidate_payload(candidate, payload)
                validate_payload_binding(candidate, payload, meta, payload)
                row.update(source_payload=legacy, native_mapping=mapping)
            records.append(row)
    require(seen == inherited.keys() | added.keys(), 'GROUP_COVERAGE')
    return dict(records=records, manifest=manifest, files=files, archive_sha256=GROUP_SHA,
                source_group_splits=groups, variant_family_splits=families)
