"""Shared checks for authored candidates and SFT export; never loads a model."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unicodedata
import zipfile

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from apps.ai.rag.base import EvidenceContext, ExerciseContext
from apps.ai.rag.citations import parse_answer, validate_choice_answer
from apps.ai.rag.context_builder import build_messages
from apps.ai.rag.guardrails import check_request_policy, parse_reading_hint
from apps.ai.providers.base import GenerationError


class InstructionError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise InstructionError(code)


def check_internal_research(resources):
    policy = resources.contract['source_rights'].get('internal_research', {})
    require(policy.get('enabled') is True and policy.get('training_experiment_allowed') is True and
            policy.get('redistribution_allowed') is False and policy.get('decision_owner') == 'A' and
            bool(policy.get('decision_reference')), 'INTERNAL_RESEARCH_NOT_AUTHORIZED')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_text_checksum(data, expected):
    if digest(data) == expected:
        return 'EXACT_BYTES'
    require(digest(data.replace(b'\r\n', b'\n')) == expected, 'BENCHMARK_CHANGED')
    return 'CRLF_TO_LF_EQUIVALENT'


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def loads(text):
    def invalid_constant(value):
        raise InstructionError('NON_FINITE_JSON')
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=invalid_constant)


def read_json(path):
    return loads(Path(path).read_text(encoding='utf-8-sig'))


def read_jsonl(path):
    return [loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def read_reviews(path):
    if Path(path).suffix.lower() != '.csv':
        return read_jsonl(path)
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)),
                'INVALID_REVIEW_HEADER')
        rows = list(reader)
    scores = ('instruction_clarity','content_correctness','grounding_and_citation',
              'task_behavior','language_and_format')
    for row in rows:
        require(None not in row and all(value is not None for value in row.values()), 'INVALID_REVIEW_CSV')
        for name in scores:
            require(row.get(name) in ('0','1','2'), 'INVALID_REVIEW_SCORE')
            row[name] = int(row[name])
        if row.get('re_review_of') == '':
            row['re_review_of'] = None
    return rows


def normalize(value):
    if isinstance(value, str):
        return unicodedata.normalize('NFC', value)
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    return value


def canonical(value):
    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def content_hash(record):
    return digest(canonical({key: value for key, value in record.items() if key != 'content_sha256'}))


def question_key(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def near_duplicate(first, second):
    def grams(text):
        key = question_key(text)
        return {key[i:i+5] for i in range(max(0, len(key)-4))}
    left, right = grams(first), grams(second)
    return bool(left and right) and len(left & right) / len(left | right) >= 0.85


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def jsonl_bytes(records):
    return b''.join(canonical(record) + b'\n' for record in records)


def guard_output(path, inputs=()):
    target = Path(path).resolve()
    protected = [ROOT/'data/qa', ROOT/'data/corpus', ROOT/'backend', ROOT/'data/instruction']
    for source in [*protected, *map(Path, inputs)]:
        source = source.resolve()
        require(not (target == source or target.is_relative_to(source) or source.is_relative_to(target)),
                'OUTPUT_OVERLAPS_INPUT')
    return target


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass
class Resources:
    contract: dict
    schema: dict
    sources: list = field(default_factory=list)
    protected_hashes: set = field(default_factory=set)
    protected_ids: set = field(default_factory=set)
    protected_questions: list = field(default_factory=list)
    root: Path = ROOT
    pdf_cache: dict = field(default_factory=dict)
    benchmark_integrity: dict = field(default_factory=dict)

    def __post_init__(self):
        Draft202012Validator.check_schema(self.schema)
        self.validator = Draft202012Validator(self.schema, format_checker=FormatChecker())
        self.catalog = {}
        for item in self.sources:
            key = (item['document_id'], item['version_id'])
            require(key not in self.catalog, 'DUPLICATE_SOURCE_IDENTITY')
            self.catalog[key] = item


def load_resources(contract_path=ROOT/'data/instruction/input-contract.json', *, preview=False, bundle=None):
    contract = read_json(contract_path)
    ref = contract['reference']
    schema_path = ROOT/'data/instruction/record-schema.json'
    require(digest(schema_path.read_bytes()) == ref['schema_sha256'], 'SCHEMA_CHECKSUM_MISMATCH')
    resources = Resources(contract, read_json(schema_path))
    # Preview is self-contained. Production also checks every protected table still present.
    for path in (ROOT/'data/qa/qa_baseline.json', ROOT/'data/qa/qa_additions.json'):
        if path.exists():
            for case in read_json(path)['cases']:
                resources.protected_questions.append(case['question'])
                resources.protected_hashes.add(digest(question_key(case['question']).encode('utf-8')))
                resources.protected_ids.add(case['qa_id'])
    if preview:
        return resources
    source = Path(bundle) if bundle else ROOT/ref['private_archive_path']
    require(source.is_file(), 'INPUT_BUNDLE_MISSING')
    require(digest(source.read_bytes()) == ref['input_archive_sha256'], 'BUNDLE_CHECKSUM_MISMATCH')
    with zipfile.ZipFile(source) as archive:
        def pinned(name, hash_name):
            data = archive.read(ref['archive_root'] + '/' + ref[name])
            require(digest(data) == ref[hash_name], 'BUNDLE_MEMBER_CHECKSUM_MISMATCH')
            return loads(data.decode('utf-8'))
        manifest = pinned('source_manifest_path_in_archive', 'source_manifest_sha256')
        exclusion = pinned('benchmark_exclusion_path_in_archive', 'benchmark_exclusion_sha256')
        training = loads(archive.read(ref['archive_root'] + '/data/instruction/w5/contract/training-format.json').decode('utf-8'))
        for name, expected in training['source_hashes'].items():
            require(digest((ROOT/name).read_bytes()) == expected, 'RUNTIME_SOURCE_CHANGED')
    require(digest((ROOT/'data/qa/source_map.json').read_bytes()) ==
            contract['input_verification']['current_source_map_sha256'], 'SOURCE_MAP_CHANGED')
    resources.sources = manifest['sources']
    resources.__post_init__()
    resources.protected_ids.update(exclusion['canonical_qa_ids'])
    for table in exclusion['protected_inputs']:
        for item in table['records']:
            if item.get('question_sha256'):
                resources.protected_hashes.add(item['question_sha256'])
        path = (ROOT/table['path']).resolve()
        require(path.is_relative_to(ROOT), 'UNSAFE_BENCHMARK_PATH')
        if path.is_file():
            resources.benchmark_integrity[table['path']] = check_text_checksum(path.read_bytes(), table['sha256'])
            if path.suffix == '.json':
                def questions(value):
                    if isinstance(value, dict):
                        if isinstance(value.get('question'), str):
                            resources.protected_questions.append(value['question'])
                        for child in value.values():
                            questions(child)
                    elif isinstance(value, list):
                        for child in value:
                            questions(child)
                questions(read_json(path))
            elif path.suffix == '.csv':
                with path.open(encoding='utf-8-sig', newline='') as stream:
                    for row in csv.DictReader(stream):
                        if row.get('question'):
                            resources.protected_questions.append(row['question'])
    return resources


def read_pdf_pages(path):
    from pypdf import PdfReader
    return [(page.extract_text() or '') for page in PdfReader(path).pages]


def validate_record(record, resources, *, preview=False, private_draft=False):
    require(not (preview and private_draft), 'PRIVATE_DRAFT_IS_NOT_FIXTURE')
    if private_draft:
        policy = resources.contract['source_rights'].get('private_research_drafts', {})
        require(policy.get('allowed') is True and policy.get('training_allowed') is False and
                policy.get('redistribution_allowed') is False, 'PRIVATE_DRAFT_NOT_AUTHORIZED')
    try:
        resources.validator.validate(record)
    except Exception as error:
        raise InstructionError('INVALID_SCHEMA') from error
    require(record['content_sha256'] == content_hash(record), 'CONTENT_HASH_MISMATCH')
    require(record['record_id'] not in resources.protected_ids and
            record['parent_record_id'] not in resources.protected_ids, 'BENCHMARK_SEED')
    require(digest(question_key(record['question']).encode('utf-8')) not in resources.protected_hashes,
            'BENCHMARK_QUESTION')
    require(not any(near_duplicate(record['question'], old) for old in resources.protected_questions),
            'BENCHMARK_NEAR_DUPLICATE_REVIEW_REQUIRED')
    is_fixture = record['source_identity_scope'] == 'fixture_only'
    require(preview == is_fixture, 'FIXTURE_SCOPE_MISMATCH')
    evidence = []
    groups = set()
    for item in record['contexts']:
        require(digest(item['text'].encode('utf-8')) == item['text_sha256'], 'TEXT_CHECKSUM_MISMATCH')
        evidence.append(EvidenceContext(**{key: item[key] for key in resources.contract['format']['evidence_context_projection']}))
        if is_fixture:
            continue
        source = resources.catalog.get((item['document_id'], item['version_id']))
        require(source is not None, 'UNKNOWN_SOURCE')
        require(source['course_code'] == record['course_code'], 'FOREIGN_COURSE_SOURCE')
        if private_draft:
            require(item['rights_reference'] == 'UNVERIFIED:' + source['source_group_id'],
                    'PRIVATE_DRAFT_RIGHTS_MARKER_REQUIRED')
        else:
            require(source.get('generation_authorized') is True and
                    source.get('rights_evidence_reference') and
                    source.get('rights_status') != 'DECLARED_NOT_VERIFIED', 'SOURCE_RIGHTS_UNVERIFIED')
            require(item['rights_reference'] == source['rights_evidence_reference'], 'RIGHTS_REFERENCE_MISMATCH')
        require(item['source_checksum'] == source['source_checksum'], 'PDF_CHECKSUM_MISMATCH')
        path = (resources.root/source['relative_path']).resolve()
        require(path.is_relative_to(resources.root.resolve()), 'UNSAFE_SOURCE_PATH')
        require(path.is_file() and digest(path.read_bytes()) == source['source_checksum'], 'PDF_CHECKSUM_MISMATCH')
        if path not in resources.pdf_cache:
            resources.pdf_cache[path] = read_pdf_pages(path)
        pages = resources.pdf_cache[path]
        require(len(pages) == source['page_count'] and 1 <= item['page_number'] <= len(pages), 'PDF_PAGE_MISMATCH')
        compact = lambda value: ''.join(unicodedata.normalize('NFC', value).split())
        require(compact(item['text']) in compact(pages[item['page_number']-1]), 'EVIDENCE_NOT_ON_PAGE')
        groups.add(source['source_group_id'])
        assigned = [x for x in resources.contract['targets']['a_sources'] if
                    x['course'] == source['course_code'] and x['document'] == source['source_doc']]
        if record['author_member'] == 'A':
            require(len(assigned) == 1 and assigned[0]['page_start'] <= item['page_number'] <= assigned[0]['page_end'],
                    'SOURCE_NOT_ASSIGNED_TO_A')
        else:
            require(not assigned, 'SOURCE_NOT_ASSIGNED_TO_B')
    require(len({e.source_id for e in evidence}) == len(evidence), 'DUPLICATE_SOURCE_ID')
    require(len({(e.document_id, e.version_id, e.chunk_id) for e in evidence}) == len(evidence), 'DUPLICATE_CHUNK')
    if is_fixture:
        require(all(group.startswith('FIXTURE:') for group in record['source_group_ids']), 'INVALID_FIXTURE_GROUP')
    else:
        require(set(record['source_group_ids']) == groups, 'SOURCE_GROUP_MISMATCH')
    exercise = ExerciseContext.from_value(record['exercise'])
    require(record['mode'] != 'qa' or exercise is None, 'EXERCISE_IN_QA')
    try:
        check_request_policy(record['question'])
        if record['task_type'] == 'hint':
            parse_reading_hint(record['target_text'], tuple(evidence))
        else:
            status, *_ = parse_answer(record['target_text'], tuple(evidence))
            expected = 'INSUFFICIENT_EVIDENCE' if record['task_type'] == 'insufficient_evidence' else 'ANSWERED'
            require(status == expected, 'TARGET_TASK_MISMATCH')
            validate_choice_answer(record['question'], record['target_text'])
    except GenerationError as error:
        raise InstructionError('TARGET_OR_REQUEST_INVALID:' + getattr(error, 'validation_reason', error.code)) from error
    provenance = record['provenance']
    if provenance['method'] == 'manual':
        require(all(provenance[key] is None for key in ('generation_model_id', 'generation_model_revision',
                                                       'generation_prompt_sha256')), 'MANUAL_MODEL_PROVENANCE')
    return tuple(evidence), exercise


def validate_records(records, resources, *, preview=False, private_draft=False):
    require(bool(records), 'EMPTY_DATASET')
    seen_ids, seen_questions = set(), []
    for record in records:
        require(record['record_id'] not in seen_ids, 'DUPLICATE_RECORD_ID')
        seen_ids.add(record['record_id'])
        validate_record(record, resources, preview=preview, private_draft=private_draft)
        question = question_key(record['question'])
        require(question not in seen_questions, 'DUPLICATE_QUESTION')
        require(not any(near_duplicate(question, old) for old in seen_questions),
                'NEAR_DUPLICATE_REVIEW_REQUIRED')
        seen_questions.append(question)


def project_sft(record, resources, *, preview=False, private_draft=False):
    evidence, exercise = validate_record(record, resources, preview=preview, private_draft=private_draft)
    messages = build_messages(record['question'], record['mode'], evidence, exercise,
                              prompt_version=resources.contract['format']['prompt_version'])
    return {'prompt': list(messages), 'completion': [{'role': 'assistant', 'content': record['target_text']}]}


def validate_reviews(records, reviews, resources):
    require(isinstance(reviews, list), 'INVALID_REVIEWS')
    fields = set(resources.contract['review_workflow']['review_fields'])
    index = {}
    ids = {record['record_id'] for record in records}
    for review in reviews:
        require(set(review) == fields and review['record_id'] in ids, 'INVALID_REVIEW_FIELDS')
        key = (review['record_id'], review['content_sha256'], review['review_kind'], review['reviewer_member'])
        require(key not in index, 'DUPLICATE_REVIEW')
        require(review['review_kind'] in ('SELF_REVIEW', 'PEER_REVIEW') and
                review['reviewer_member'] in ('A', 'B') and
                review['decision'] in ('ACCEPT', 'REVISE', 'REJECT'), 'INVALID_REVIEW')
        try:
            date = datetime.fromisoformat(review['reviewed_at'])
            require(date.tzinfo is not None, 'REVIEW_TIMEZONE_REQUIRED')
        except (ValueError, TypeError) as error:
            raise InstructionError('INVALID_REVIEW_DATE') from error
        require(isinstance(review['reason'], str) and bool(review['reason'].strip()), 'REVIEW_REASON_REQUIRED')
        index[key] = review
    accepted = {}
    criteria = ['instruction_clarity', 'content_correctness', 'grounding_and_citation',
                'task_behavior', 'language_and_format']
    for record in records:
        key = (record['record_id'], record['content_sha256'], 'SELF_REVIEW', record['author_member'])
        require(key in index, 'SELF_REVIEW_MISSING_OR_STALE')
        review = index[key]
        require(review['decision'] == 'ACCEPT', 'REVIEW_NOT_ACCEPTED')
        scores = [review[name] for name in criteria]
        require(all(type(score) is int and score in (1, 2) for score in scores) and sum(scores) >= 9,
                'REVIEW_SCORE_FAILED')
        require(all(review[name] == 2 for name in ('content_correctness','grounding_and_citation','task_behavior')),
                'REVIEW_CRITICAL_SCORE_FAILED')
        # A later REVISE/REJECT of the same content cannot be hidden behind an old ACCEPT.
        require(not any(row['record_id'] == record['record_id'] and row['content_sha256'] == record['content_sha256']
                        and row['decision'] != 'ACCEPT' for row in reviews), 'UNRESOLVED_REVIEW_FINDING')
        accepted[record['record_id']] = deepcopy(review)
    return accepted
