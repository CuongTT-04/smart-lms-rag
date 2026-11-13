"""Hash-bound benchmark revisions and split checks, independent of model generation."""
from collections import Counter
from copy import deepcopy
import csv
import json
from pathlib import Path
import re
import unicodedata

from scripts.qlora.data import digest, read_rows, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory, write_json

CONTENT_FIELDS = ('question', 'scope_id', 'course_code', 'question_type', 'answerable', 'reference')
REVIEW_FIELDS = ('qa_id', 'content_sha256', 'review_kind', 'reviewer', 'agent_run_id',
                 'question_valid', 'reference_correct_complete', 'pages_support', 'nonduplicate',
                 'absence_checked_full_scope', 'decision', 'reason', 'source_check',
                 'duplicate_check', 'absence_check')


def content_digest(row):
    return digest({key: row[key] for key in CONTENT_FIELDS})


def normalized_question(value):
    text = unicodedata.normalize('NFC', value).casefold()
    return ' '.join(re.findall(r'\w+', text))


def atomic_points(points):
    """Split explicit clauses, but keep a bare yes/no attached to its explanation."""
    result = []
    for point in points:
        clauses = [part.strip() for part in point.split(';') if part.strip()]
        if len(clauses) > 1 and normalized_question(clauses[0]) in {'không', 'có', 'chưa'}:
            clauses[:2] = ['; '.join(clauses[:2])]
        result.extend(clauses)
    return result


def validate_reviews(records, reviews, require_approval=True):
    expected = {row['qa_id']: row for row in records}
    require(len(expected) == len(records) and bool(records), 'REVIEW_CASE_IDS')
    seen = set()
    for review in reviews:
        rid = review['qa_id']
        require(rid in expected and rid not in seen, 'REVIEW_UNKNOWN_OR_DUPLICATE')
        seen.add(rid)
        row = expected[rid]
        require(content_digest(row) == row['content_sha256'] == review['content_sha256'], 'STALE_REVIEW')
        require(review['review_kind'] == 'AGENT_REVIEW', 'REVIEW_PROVENANCE')
        for field in ('question_valid', 'reference_correct_complete', 'pages_support', 'nonduplicate'):
            require(review[field] in {'YES', 'NO', 'PENDING'}, 'REVIEW_CRITERION')
            if require_approval:
                require(review[field] == 'YES', 'REVIEW_UNRESOLVED')
        for field in ('reviewer', 'agent_run_id', 'reason', 'source_check', 'duplicate_check'):
            require(isinstance(review.get(field), str) and review[field].strip(), 'REVIEW_NOTE_REQUIRED')
        require(review['decision'] in {'APPROVE', 'REVISE', 'REJECT'}, 'REVIEW_DECISION')
        if require_approval or review['decision'] == 'APPROVE':
            require(review['decision'] == 'APPROVE' and all(review[k] == 'YES' for k in
                    ('question_valid', 'reference_correct_complete', 'pages_support', 'nonduplicate')), 'REVIEW_UNRESOLVED')
        if not row['answerable']:
            require(review['absence_checked_full_scope'] == 'YES' and review['absence_check'].strip(), 'ABSENCE_REVIEW_REQUIRED')
    require(seen == set(expected), 'REVIEW_INCOMPLETE')


def split_audit(records, metadata, payloads):
    """Prove source partitioning; do not infer semantic novelty from string matching."""
    require(len(metadata) == len(payloads), 'LEAKAGE_INPUT_LENGTHS')
    scope = {e['source_group_id'] for row in records for e in row['reference']['evidence']}
    groups, families, questions = {}, {}, {}
    counts = Counter()
    ids = set()
    for meta, payload in zip(metadata, payloads):
        split, rid = meta['split'], meta['record_id']
        require(rid not in ids, 'LEAKAGE_DUPLICATE_ID')
        ids.add(rid)
        counts[split] += 1
        for group in meta['source_group_ids']:
            require(group not in groups or groups[group] == split, 'GROUP_SPLIT_LEAKAGE')
            groups[group] = split
        family = meta['variant_family_id']
        require(family not in families or families[family] == split, 'FAMILY_SPLIT_LEAKAGE')
        families[family] = split
        user = json.loads(payload['prompt'][-1]['content'])
        question = user.get('question', user.get('instruction', ''))
        if question:
            questions.setdefault(normalized_question(question), []).append((rid, split))
    overlap = sorted(group for group in scope if groups.get(group) in {'train', 'validation'})
    exact = [{'qa_id': row['qa_id'], 'matches': questions[normalized_question(row['question'])]}
             for row in records if normalized_question(row['question']) in questions]
    main_questions = [normalized_question(row['question']) for row in records]
    require(len(set(main_questions)) == len(records), 'MAIN_EXACT_DUPLICATE')
    require(not overlap, 'MAIN_SOURCE_IN_TRAIN_OR_VALIDATION')
    require(not any(split != 'instruction_holdout' for item in exact for _, split in item['matches']), 'MAIN_EXACT_TRAIN_LEAKAGE')
    return dict(status='SOURCE_SPLITS_AND_EXACT_QUESTIONS_CHECKED', split_counts=dict(counts),
                main_source_groups=sorted(scope), train_validation_source_overlap=overlap,
                exact_instruction_question_matches=exact, group_and_family_disjoint=True,
                holdout_used_for_training_or_selection=False,
                semantic_novelty='NOT_PROVEN_BY_STRING_MATCHING',
                limitation='Related concepts and paraphrases require the separate content review. Shared retrieval sources are not training examples.')


def duplicate_audit(records, metadata, payloads, threshold=0.85):
    """Flag exact/5-character-gram overlaps; never equate lexical scores to semantics."""
    from scripts.w5.common import ngrams
    require(len(metadata) == len(payloads), 'DUPLICATE_INPUT_LENGTHS')
    entries = []
    for meta, payload in zip(metadata, payloads):
        user = json.loads(payload['prompt'][-1]['content'])
        target = payload['completion'][0]['content']
        if target.startswith('{'):
            target = ' '.join(item['text'] for item in json.loads(target)['items'])
        entries.append(dict(record_id=meta['record_id'], split=meta['split'],
            question=normalized_question(user['question']), target=normalized_question(target)))
    questions = [ngrams(row['question']) for row in entries]
    targets = [ngrams(row['target']) if len(row['target']) >= 80 else None for row in entries]
    def score(left, right):
        if left is None or right is None or not left or not right:
            return 0.0
        if min(len(left), len(right)) / max(len(left), len(right)) < threshold:
            return 0.0
        return len(left & right) / len(left | right)
    findings = []
    for i, left in enumerate(entries):
        for j in range(i):
            for kind, value in (('QUESTION', score(questions[i], questions[j])), ('TARGET', score(targets[i], targets[j]))):
                if value >= threshold:
                    findings.append(dict(kind=kind, left=left['record_id'], right=entries[j]['record_id'],
                        left_split=left['split'], right_split=entries[j]['split'], score=value))
    main_findings = []
    for row in records:
        query = ngrams(normalized_question(row['question']))
        target = normalized_question(' '.join(row['reference']['required_points']))
        target_grams = ngrams(target) if len(target) >= 80 else None
        for index, entry in enumerate(entries):
            for kind, value in (('QUESTION', score(query, questions[index])), ('TARGET', score(target_grams, targets[index]))):
                if value >= threshold:
                    main_findings.append(dict(qa_id=row['qa_id'], record_id=entry['record_id'],
                        split=entry['split'], kind=kind, score=value))
    return dict(records_checked=len(entries), benchmark_cases=len(records), threshold=threshold,
        algorithm='NFC_CASEFOLD_WORD_NORMALIZATION_AND_CHARACTER_5GRAM_JACCARD',
        short_or_refusal_or_hint_targets_excluded_below_characters=80,
        internal_findings=findings, benchmark_findings=main_findings,
        limitation='Lexical screening only. Flags require review; a zero count does not prove semantic independence.')


def revise(records, replacements):
    result, changes = [], []
    require(set(replacements) <= {row['qa_id'] for row in records}, 'UNKNOWN_REPLACEMENT_ID')
    for original in records:
        require(content_digest(original) == original['content_sha256'], 'ORIGINAL_CONTENT_CHANGED')
        row = deepcopy(original)
        if row['qa_id'] in replacements:
            patch = replacements[row['qa_id']]
            row['question'] = patch['question']
            row['reference']['required_points'] = patch['required_points']
            row['reference']['evidence'] = deepcopy(patch['evidence'])
            row['author_member'] = patch['author_member']
        row['reference']['required_points'] = atomic_points(row['reference']['required_points'])
        row['content_sha256'] = content_digest(row)
        if row['content_sha256'] != original['content_sha256']:
            changes.append(dict(qa_id=row['qa_id'], old_content_sha256=original['content_sha256'],
                                new_content_sha256=row['content_sha256'],
                                question_changed=row['question'] != original['question'],
                                old_question=original['question'], new_question=row['question']))
        result.append(row)
    return result, changes


def write_package(output, records, reviews, changes, leakage, provenance):
    """Persist already authored decisions; this function never decides approval."""
    output = Path(output)
    require(not output.exists(), 'NEW_BENCHMARK_OUTPUT_REQUIRED')
    validate_reviews(records, reviews, require_approval=False)
    output.mkdir(parents=True)
    (output / 'main.references.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8')
    inputs = [{key: row[key] for key in ('qa_id', 'question', 'scope_id')} for row in records]
    (output / 'main.inputs.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in inputs), encoding='utf-8')
    with (output / 'reviews.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(reviews)
    write_json(output / 'changes.json', changes)
    write_json(output / 'leakage-audit.json', leakage)
    refresh = [row['qa_id'] for row in changes if row['question_changed']]
    unresolved = [row['qa_id'] for row in reviews if row['decision'] != 'APPROVE']
    write_json(output / 'readiness.json', dict(status='BENCHMARK_REQUIRES_REVISION' if unresolved else 'REVIEWED_BENCHMARK_PENDING_INPUT_REFRESH',
        cases=len(records), answerable=sum(row['answerable'] for row in records),
        insufficient=sum(not row['answerable'] for row in records),
        question_ids_requiring_retrieval_refresh=refresh, unresolved_review_ids=unresolved,
        model_input_export_required=True, main_authorized=False, training='NOT_RUN', **provenance))
    write_json(output / 'manifest.json', dict(files=inventory(output), references_sha256=sha_file(output / 'main.references.jsonl')))
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    verify_inventory(output, manifest['files'])
    require(set(inventory(output, ('manifest.json',))) == set(manifest['files']), 'BENCHMARK_FILE_SET')
    validate_reviews(read_rows(output / 'main.references.jsonl'), reviews, require_approval=False)
