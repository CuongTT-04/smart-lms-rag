"""Lock independent B reviews and combine the frozen three-arm experiment."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import random

from scripts.comparison.main_scoring import assignment, paired, parse, quantile, semantic_metrics
from scripts.comparison.protocol import digest, file_hash, read_rows, validate_cache, write_json, write_rows
from scripts.comparison.runner import audit_outputs
from scripts.qlora.data import read_json, require
from scripts.qlora.runtime import inventory, verify_inventory

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / '.private/comparison'
SOURCE = DATA / 'assessment/main'
ARMS = ('base', 'rag', 'tuned_rag')


def policy_score(case, raw_score):
    if case['generation_status'] != 'completed':
        return 0
    if not case['answerable'] and not case['parsed']['schema_valid']:
        return 0
    if case['answerable'] and case['parsed']['schema_valid'] and not case['parsed']['items']:
        return 0
    return raw_score


def build_review(case, note, reviewer):
    require(note['blind_id'] == case['blind_id'], 'B_NOTE_ID')
    score = note['raw_content_score']
    require(type(score) is int and score in (0, 1, 2), 'B_SCORE')
    require(isinstance(note['reason'], str) and note['reason'].strip(), 'B_REASON')
    items = case['parsed']['items'] if case['contexts'] else []
    require(len(note['verdicts']) == len(note['claim_reasons']) == len(items), 'B_ITEM_REVIEW_COUNT')
    claims = []
    for i, (item, verdict, reason) in enumerate(zip(items, note['verdicts'], note['claim_reasons'])):
        require(isinstance(reason, str) and reason.strip(), 'B_ITEM_REASON')
        require(isinstance(verdict, str) and bool(verdict), 'B_ITEM_VERDICT')
        ids = [] if verdict in ('u', 'n') else verdict.lstrip('!').split('+')
        require(len(ids) == len(set(ids)) and all(eid in case['contexts'] for eid in ids), 'B_SOURCE_ID')
        status = ('nonassertion' if verdict == 'n' else 'contradicted' if verdict.startswith('!')
                  else 'supported' if ids else 'unsupported')
        sources = []
        for eid in ids:
            context = case['contexts'][eid]
            sources.append(dict(evidence_id=eid, quote=context['text'], **{key: context[key] for key in
                ('document_id', 'version_id', 'page_number', 'char_start', 'char_end', 'source_checksum')}))
        claims.append(dict(item_index=i, claim=item['text'], status=status, sources=sources,
            citation_id=item['evidence_id'], citation_supported=status == 'supported' and ids == [item['evidence_id']],
            reason=reason, method='INDEPENDENT_BLINDED_SEMANTIC_CONTEXT_REVIEW'))
    return dict(blind_id=case['blind_id'], qa_id=case['qa_id'],
        content_sha256=case['content_sha256'], raw_output_sha256=case['raw_output_sha256'],
        reference_sha256=case['reference_sha256'], correctness=policy_score(case, score),
        raw_content_score=score, reason=note['reason'], required_points=case['reference']['required_points'],
        required_points_review='SEE_SOURCE_GROUNDED_RATIONALE', claims=claims,
        reviewer=reviewer, assessment_kind='AUTOMATED_RUBRIC')


def validate_reviews(cases, reviews, expected_ids, reviewer):
    result = {}
    for row in reviews:
        bid = row['blind_id']
        require(bid in expected_ids and bid not in result and bid in cases, 'GROUP_REVIEW_ID_SET')
        case = cases[bid]
        require(row['reviewer'] == reviewer and row['assessment_kind'] == 'AUTOMATED_RUBRIC', 'GROUP_REVIEWER')
        for key in ('qa_id', 'content_sha256', 'raw_output_sha256', 'reference_sha256'):
            require(row[key] == case[key], 'GROUP_STALE_REVIEW:' + key)
        require(type(row['raw_content_score']) is int and row['raw_content_score'] in (0, 1, 2), 'GROUP_RAW_SCORE')
        require(type(row['correctness']) is int and row['correctness'] == policy_score(case, row['raw_content_score']),
                'GROUP_FAILURE_SCORE_POLICY')
        require(isinstance(row['reason'], str) and row['reason'].strip(), 'GROUP_REASON')
        require(row['required_points'] == case['reference']['required_points'], 'GROUP_REQUIRED_POINTS_CHANGED')
        items = case['parsed']['items'] if case['contexts'] else []
        require(len(row['claims']) == len(items), 'GROUP_CLAIM_COUNT')
        for i, claim in enumerate(row['claims']):
            require(claim['item_index'] == i and claim['claim'] == items[i]['text'], 'GROUP_CLAIM_IDENTITY')
            require(claim['status'] in ('supported', 'unsupported', 'contradicted', 'nonassertion'), 'GROUP_CLAIM_STATUS')
            if claim['status'] != 'nonassertion':
                require(claim.get('citation_id') == items[i]['evidence_id'], 'GROUP_CITATION_ID_CHANGED')
            require(isinstance(claim['reason'], str) and claim['reason'].strip(), 'GROUP_CLAIM_REASON')
            ids = [s['evidence_id'] for s in claim['sources']]
            require(len(ids) == len(set(ids)), 'GROUP_DUPLICATE_SOURCE')
            for source in claim['sources']:
                eid = source['evidence_id']
                require(eid in case['contexts'], 'GROUP_UNKNOWN_SOURCE')
                context = case['contexts'][eid]
                require(source['quote'] == context['text'], 'GROUP_INVENTED_SOURCE_QUOTE')
                for key in ('document_id', 'version_id', 'page_number', 'char_start', 'char_end', 'source_checksum'):
                    require(source[key] == context[key], 'GROUP_SOURCE_BINDING')
            require(bool(ids) == (claim['status'] in ('supported', 'contradicted')), 'GROUP_SUPPORT_EVIDENCE')
            supported_citation = claim['status'] == 'supported' and ids == [items[i]['evidence_id']]
            require(type(claim['citation_supported']) is bool and claim['citation_supported'] == supported_citation,
                    'GROUP_CITATION_SUPPORT')
        result[bid] = row
    require(set(result) == set(expected_ids), 'GROUP_MISSING_REVIEW')
    return result


def signature(review):
    return (review['correctness'], tuple((c['status'], c['citation_supported']) for c in review['claims']))


def agreement(primary, secondary):
    require(bool(primary) and set(primary) == set(secondary), 'GROUP_AGREEMENT_ID_SET')
    matrix = [[0] * 3 for _ in range(3)]
    for bid, left in primary.items():
        matrix[left['correctness']][secondary[bid]['correctness']] += 1
    n = len(primary)
    observed = sum(matrix[i][i] for i in range(3)) / n
    expected = sum(sum(matrix[i]) * sum(row[i] for row in matrix) for i in range(3)) / n**2
    return dict(pairs=n, exact_correctness_agreement=observed, confusion_matrix=matrix,
                cohen_kappa=(observed - expected) / (1 - expected) if expected < 1 else None,
                unit='Independent automated reviews of the same output; not human inter-rater reliability.')


def resolve_reviews(primary, secondary, decisions):
    require(set(secondary).issubset(primary), 'GROUP_SECONDARY_WITHOUT_PRIMARY')
    conflicts = {bid for bid in secondary if signature(primary[bid]) != signature(secondary[bid])}
    require(set(decisions) == conflicts, 'GROUP_UNRESOLVED_OR_UNREQUESTED_ADJUDICATION')
    final = dict(primary)
    log = []
    for bid in sorted(secondary):
        chosen = decisions[bid] if bid in conflicts else primary[bid]
        final[bid] = chosen
        log.append(dict(blind_id=bid, disputed=bid in conflicts,
            primary_reviewer=primary[bid]['reviewer'], secondary_reviewer=secondary[bid]['reviewer'],
            primary_correctness=primary[bid]['correctness'], secondary_correctness=secondary[bid]['correctness'],
            final_correctness=chosen['correctness'], decision_reason=chosen['reason'],
            primary_review_sha256=digest(primary[bid]), secondary_review_sha256=digest(secondary[bid]),
            final_review_sha256=digest(chosen)))
    return list(final.values()), log


def load_inputs():
    """Bind packets, assignments and reference hashes to the original 900 outputs."""
    verify_inventory(SOURCE, read_json(SOURCE / 'manifest.json')['files'])
    lock = read_json(SOURCE / 'reviews-lock.json')
    for name, key in (('reviews-a.jsonl', 'reviews_sha256'), ('review-notes.json', 'notes_sha256'),
                      ('blinded.jsonl', 'blinded_sha256'), ('judge-config.json', 'judge_config_sha256')):
        require(file_hash(SOURCE / name) == lock[key], 'GROUP_A_LOCK_CHANGED')
    raw_path = DATA / 'runs/main-intake/main-20261113T011502419787Z/outputs.jsonl'
    refs_path = DATA / 'prepared/benchmark-v3/main.references.jsonl'
    judge = read_json(SOURCE / 'judge-config.json')
    require(file_hash(raw_path) == judge['locked_raw_sha256'] and file_hash(refs_path) == judge['references_sha256'],
            'GROUP_RAW_OR_REFERENCE_CHANGED')
    refs = read_rows(refs_path)
    refmap = {r['qa_id']: r for r in refs}
    require(len(refs) == len(refmap) == 300, 'GROUP_FULL_BENCHMARK_REQUIRED')
    caches = read_rows(DATA / 'prepared/retrieval-v2/main.cache.jsonl')
    cachemap = {r['qa_id']: r for r in caches}
    require(len(caches) == len(cachemap) == 300 and set(cachemap) == set(refmap), 'GROUP_CACHE_ID_SET')
    for cache in caches:
        validate_cache(cache)
    raw = read_rows(raw_path)
    models = read_rows(DATA / 'prepared/main-runner-fixed/contents/inputs/main.model-inputs.jsonl')
    config = read_json(DATA / 'prepared/frozen-experiment/run-config.json')
    audit_outputs(models, raw, config['adapter_sha256'])
    require(len(raw) == 900 and {r['qa_id'] for r in raw} == set(refmap), 'GROUP_FULL_MAIN_REQUIRED')
    random.Random(42).shuffle(raw)
    packets = read_rows(SOURCE / 'blinded.jsonl')
    cases = {c['blind_id']: c for c in packets}
    mapping_rows = read_rows(SOURCE / 'mapping.PRIVATE.jsonl')
    mapping = {m['blind_id']: m for m in mapping_rows}
    require(len(packets) == len(cases) == len(mapping_rows) == len(mapping) == 900, 'GROUP_BLIND_ID_SET')
    owners, asecondary = assignment(refs)
    bsecondary = set()
    for course in ('CNXHKH', 'KTCTMLN', 'THMLN'):
        for kind in ('factual', 'explanation', 'multi_page', 'insufficient'):
            ids = sorted(r['qa_id'] for r in refs if owners[r['qa_id']] == 'A'
                         and r['course_code'] == course and r['question_type'] == kind)
            random.Random('42:Bsecondary:' + course + ':' + kind).shuffle(ids)
            bsecondary.update(ids[:2 if kind == 'factual' else 1])
    roles = {owner: {'primary': set(), 'secondary': set()} for owner in ('A', 'B')}
    for i, row in enumerate(raw, 1):
        bid = f'M{i:03}'
        require(bid in cases and bid in mapping, 'GROUP_BLIND_ID_MISSING')
        case, meta = cases[bid], mapping[bid]
        ref = refmap[row['qa_id']]
        contexts = {} if row['arm'] == 'base' else {
            f'E{j}.1': c for j, c in enumerate(cachemap[row['qa_id']]['contexts'], 1)}
        require(meta['qa_id'] == case['qa_id'] == row['qa_id'] and meta['arm'] == row['arm']
                and meta['output_record_sha256'] == digest(row), 'GROUP_BLIND_MAPPING_CHANGED')
        for key in ('run_id', 'generation_seconds', 'input_tokens', 'output_tokens'):
            require(meta[key] == row[key], 'GROUP_MEASUREMENT_BINDING:' + key)
        require(case['raw_output'] == row['raw_output'] and case['raw_output_sha256'] == digest(row['raw_output'])
                and case['reference'] == ref['reference'] and case['reference_sha256'] == digest(ref)
                and case['content_sha256'] == ref['content_sha256'] and case['question'] == ref['question']
                and case['answerable'] == ref['answerable'] and case['contexts'] == contexts
                and case['course_code'] == ref['course_code'] and case['question_type'] == ref['question_type']
                and case['generation_status'] == row['status'] and case['parsed'] == parse(row['raw_output']),
                'GROUP_PACKET_OR_REFERENCE_CHANGED')
        owner = owners[row['qa_id']]
        roles[owner]['primary'].add(bid)
        if row['qa_id'] in asecondary:
            roles['A']['secondary'].add(bid)
        if row['qa_id'] in bsecondary:
            roles['B']['secondary'].add(bid)
    for role in roles.values():
        require(len(role['primary']) == 450 and len(role['secondary']) == 45, 'GROUP_ASSIGNMENT_QUOTA')
    return cases, mapping, roles


def lock_b(notes_paths, output):
    require(not output.exists(), 'NEW_B_REVIEW_FOLDER_REQUIRED')
    cases, _, roles = load_inputs()
    notes = [row for path in notes_paths for row in read_rows(path)]
    reviews = [build_review(cases[n['blind_id']], n, 'B') for n in notes]
    ids = roles['B']['primary'] | roles['B']['secondary']
    validate_reviews(cases, reviews, ids, 'B')
    output.mkdir(parents=True)
    write_rows(output / 'reviews-b.jsonl', reviews)
    judge = read_json(SOURCE / 'judge-config.json')
    judge.update(reviewer='B', engine='INDEPENDENT_BLINDED_AGENT_REVIEW_THREE_DISJOINT_BATCHES',
                 exact_model_revision=None, decoding_temperature=None, seed=None,
                 seed_note='42 fixes the review assignment; host-agent decoding seed is not exposed.',
                 same_judge_revision_as_A='NOT_VERIFIABLE_HOST_METADATA_UNAVAILABLE')
    write_json(output / 'judge-config.json', judge)
    write_json(output / 'reviews-lock.json', dict(
        reviews_sha256=file_hash(output / 'reviews-b.jsonl'),
        judge_config_sha256=file_hash(output / 'judge-config.json'),
        source_a_reviews_lock_sha256=file_hash(SOURCE / 'reviews-lock.json'),
        notes=[dict(path=str(path), sha256=file_hash(path)) for path in notes_paths],
        assignment_counts={k: len(v) for k, v in roles['B'].items()},
        assessment_kind='AUTOMATED_RUBRIC', human_review=False))
    return reviews


def verify_b_lock(folder):
    lock = read_json(folder / 'reviews-lock.json')
    require(file_hash(folder / 'reviews-b.jsonl') == lock['reviews_sha256']
            and file_hash(folder / 'judge-config.json') == lock['judge_config_sha256'], 'GROUP_B_LOCK_CHANGED')
    require(file_hash(SOURCE / 'reviews-lock.json') == lock['source_a_reviews_lock_sha256'],
            'GROUP_B_FROM_DIFFERENT_A_REVISION')
    a_judge = read_json(SOURCE / 'judge-config.json')
    b_judge = read_json(folder / 'judge-config.json')
    for key in ('rubric_sha256', 'claim_unit', 'failure_policy', 'locked_raw_sha256', 'references_sha256'):
        require(a_judge[key] == b_judge[key], 'GROUP_B_ASSESSMENT_POLICY_CHANGED:' + key)
    return lock


def validate_renderers(cases, rows):
    renders = {r['blind_id']: r for r in rows}
    require(len(rows) == len(renders) == len(cases) and set(renders) == set(cases), 'GROUP_RENDERER_ID_SET')
    for bid, row in renders.items():
        require(row['raw_output_sha256'] == cases[bid]['raw_output_sha256'], 'GROUP_RENDERER_BINDING')
        grounded = bool(cases[bid]['contexts'])
        valid_statuses = ('RENDERED', 'BLOCKED') if grounded else ('PROTOCOL_VALID', 'PROTOCOL_INVALID')
        require(row['backend_renderer_applied'] is grounded and row['status'] in valid_statuses,
                'GROUP_RENDERER_METHOD')
    return renders


def prepare_adjudication(b_folder, output):
    require(not output.exists(), 'NEW_ADJUDICATION_FOLDER_REQUIRED')
    cases, _, roles = load_inputs()
    a = validate_reviews(cases, read_rows(SOURCE / 'reviews-a.jsonl'),
                         roles['A']['primary'] | roles['A']['secondary'], 'A')
    verify_b_lock(b_folder)
    b = validate_reviews(cases, read_rows(b_folder / 'reviews-b.jsonl'),
                         roles['B']['primary'] | roles['B']['secondary'], 'B')
    primary = {bid: (a if bid in roles['A']['primary'] else b)[bid] for bid in cases}
    secondary = {**{bid: a[bid] for bid in roles['A']['secondary']},
                 **{bid: b[bid] for bid in roles['B']['secondary']}}
    require(len(primary) == 900 and len(secondary) == 90, 'GROUP_PRIMARY_SECONDARY_COUNTS')
    output.mkdir(parents=True)
    result = agreement({bid: a[bid] for bid in secondary}, {bid: b[bid] for bid in secondary})
    result['matrix_axes'] = ['reviewer_A', 'reviewer_B']
    write_json(output / 'agreement.json', result)
    disputed = [dict(case=cases[bid], primary=primary[bid], secondary=secondary[bid]) for bid in sorted(secondary)
                if signature(primary[bid]) != signature(secondary[bid])]
    write_rows(output / 'disputes.jsonl', disputed)
    write_json(output / 'intake.json', dict(primary=900, secondary=90, disputes=len(disputed),
        a_lock_sha256=file_hash(SOURCE / 'reviews-lock.json'),
        b_lock_sha256=file_hash(b_folder / 'reviews-lock.json'),
        disputes_sha256=file_hash(output / 'disputes.jsonl')))
    return cases, primary, secondary, disputed


def aggregate(b_folder, adjudication, output):
    require(not output.exists(), 'NEW_GROUP_RESULT_FOLDER_REQUIRED')
    cases, mapping, roles = load_inputs()
    verify_b_lock(b_folder)
    reviews = {owner: validate_reviews(cases, read_rows(path), roles[owner]['primary'] | roles[owner]['secondary'], owner)
               for owner, path in [('A', SOURCE / 'reviews-a.jsonl'), ('B', b_folder / 'reviews-b.jsonl')]}
    primary = {bid: reviews['A' if bid in roles['A']['primary'] else 'B'][bid] for bid in cases}
    secondary = {bid: reviews[owner][bid] for owner in ('A', 'B') for bid in roles[owner]['secondary']}
    disputed = {bid for bid in secondary if signature(primary[bid]) != signature(secondary[bid])}
    decisions = [build_review(cases[n['blind_id']], n, 'ADJUDICATOR') for n in read_rows(adjudication)]
    decision_map = validate_reviews(cases, decisions, disputed, 'ADJUDICATOR')
    final, decision_log = resolve_reviews(primary, secondary, decision_map)
    renders = validate_renderers(cases, read_rows(SOURCE / 'renderer.jsonl'))
    records = []
    original_records = []
    for row in final:
        bid = row['blind_id']
        case, meta, rendered = cases[bid], mapping[bid], renders[bid]
        require(rendered['raw_output_sha256'] == case['raw_output_sha256'], 'GROUP_RENDERER_BINDING')
        extras = dict(arm=meta['arm'], review_role='primary', course_code=case['course_code'],
            question_type=case['question_type'], answerable=case['answerable'],
            schema_valid=case['parsed']['schema_valid'],
            protocol_abstention=case['parsed']['schema_valid'] and not case['parsed']['items'],
            generation_status=case['generation_status'], generation_seconds=meta['generation_seconds'],
            render_status=rendered['status'])
        records.append(dict(row, **extras, displayed_correctness=row['correctness']
                            if rendered['status'] in ('RENDERED', 'PROTOCOL_VALID') else 0))
        original = primary[bid]
        original_records.append(dict(original, **extras, displayed_correctness=original['correctness']
                                     if rendered['status'] in ('RENDERED', 'PROTOCOL_VALID') else 0))

    def metrics(rows):
        result = {}
        for arm in ARMS:
            result[arm] = semantic_metrics([r for r in rows if r['arm'] == arm])
            if arm == 'base':
                for key in ('supported_items', 'eligible_assertion_items', 'citation_attempt_items',
                            'supported_citation_items', 'no_assertion_outputs'):
                    result[arm][key] = None
        return result

    comparisons = [paired(records, left, right) for left, right in
                   (('base', 'rag'), ('rag', 'tuned_rag'), ('base', 'tuned_rag'))]
    technical = {}
    for arm in ARMS:
        selected = [bid for bid in cases if mapping[bid]['arm'] == arm]
        times = [mapping[bid]['generation_seconds'] for bid in selected]
        technical[arm] = dict(outputs=len(selected),
            status_counts=dict(Counter(cases[bid]['generation_status'] for bid in selected)),
            raw_json_valid=sum(cases[bid]['parsed']['json_valid'] for bid in selected),
            schema_valid=sum(cases[bid]['parsed']['schema_valid'] for bid in selected),
            renderer_or_base_protocol_valid=sum(renders[bid]['status'] in ('RENDERED', 'PROTOCOL_VALID') for bid in selected),
            backend_renderer_eligible=arm != 'base',
            protocol_abstentions=sum(cases[bid]['parsed']['schema_valid'] and not cases[bid]['parsed']['items'] for bid in selected),
            generation_mean_seconds=sum(times) / len(times), generation_p50_seconds=quantile(times, .5),
            generation_p95_seconds=quantile(times, .95), generation_seconds_sum=sum(times),
            input_tokens=sum(mapping[bid]['input_tokens'] for bid in selected),
            output_tokens=sum(mapping[bid]['output_tokens'] for bid in selected))
    summary = dict(status='GROUP_900_PRIMARY_90_SECONDARY_ADJUDICATED', assessment_kind='AUTOMATED_RUBRIC',
        primary_outputs=900, primary_questions=300, secondary_outputs=90,
        pre_adjudication_metrics=metrics(original_records), primary_metrics=metrics(records),
        all_900_technical_metrics=technical,
        by_course={course: metrics([r for r in records if r['course_code'] == course])
                   for course in ('CNXHKH', 'KTCTMLN', 'THMLN')},
        by_type={kind: metrics([r for r in records if r['question_type'] == kind])
                 for kind in ('factual', 'explanation', 'multi_page', 'insufficient')},
        agreement=dict(agreement({bid: reviews['A'][bid] for bid in secondary},
                                 {bid: reviews['B'][bid] for bid in secondary}),
                       matrix_axes=['reviewer_A', 'reviewer_B']),
        adjudicated_outputs=len(disputed), paired=[{k: v for k, v in c.items() if k != 'pairs'} for c in comparisons],
        retrieval=read_json(SOURCE / 'retrieval-summary.json'),
        limitations=[
            'Automated source-grounded rubric assessment; exact host judge revision and decoding are unavailable.',
            'Independent B batches were blinded to A scores and arm mapping. Output content can still reveal a method.',
            'Faithfulness/citations use conservative structured items; compound items require all subclaims supported.',
            'Unparseable, empty and nonassertion outputs are excluded from support ratios and counted separately.',
            'Three output_limit generations remain in all denominators and score zero in primary correctness.',
            'Base source-support/citation measures are not applicable. Shared retrieval is one common result.',
            'Paired bootstrap covers question sampling, not judge uncertainty or training-run variability.',
            'Benchmark contains disclosed conceptual overlap; conclusions are limited to the frozen three-course test.',
        ])
    output.mkdir(parents=True)
    write_rows(output / 'scored-group.jsonl', records)
    write_rows(output / 'primary-before-adjudication.jsonl', original_records)
    write_rows(output / 'adjudication.jsonl', decision_log)
    write_rows(output / 'adjudicated-reviews.jsonl', decisions)
    write_json(output / 'summary.json', summary)
    write_json(output / 'paired.json', comparisons)
    metric_rows = []
    for scope, table in [('GROUP_ADJUDICATED_300_QUESTIONS_PER_ARM', summary['primary_metrics']),
                         ('GROUP_INDEPENDENT_PRIMARY_BEFORE_ADJUDICATION', summary['pre_adjudication_metrics'])]:
        metric_rows.extend(dict(scope=scope, arm=arm, **table[arm]) for arm in ARMS)
    for kind in ('by_course', 'by_type'):
        for label, table in summary[kind].items():
            metric_rows.extend(dict(scope=kind + ':' + label, arm=arm, **table[arm]) for arm in ARMS)
    with (output / 'metrics.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(metric_rows[0]))
        writer.writeheader()
        writer.writerows(metric_rows)
    errors = [dict(blind_id=r['blind_id'], qa_id=r['qa_id'], arm=r['arm'], course=r['course_code'],
                   question_type=r['question_type'], correctness=r['correctness'], reason=r['reason'],
                   generation_status=r['generation_status'], render_status=r['render_status']) for r in records
              if r['correctness'] < 2 or r['render_status'] not in ('RENDERED', 'PROTOCOL_VALID')]
    with (output / 'errors.csv').open('w', encoding='utf-8', newline='') as f:
        fields = ['blind_id', 'qa_id', 'arm', 'course', 'question_type', 'correctness', 'reason',
                  'generation_status', 'render_status']
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(errors)
    write_json(output / 'manifest.json', dict(scorer_sha256=file_hash(__file__),
        original_a_manifest_sha256=file_hash(SOURCE / 'manifest.json'),
        original_a_lock_sha256=file_hash(SOURCE / 'reviews-lock.json'),
        b_lock_sha256=file_hash(b_folder / 'reviews-lock.json'),
        adjudication_notes_sha256=file_hash(adjudication), files=inventory(output, ('manifest.json',))))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('lock-b', 'prepare-adjudication', 'aggregate'))
    parser.add_argument('--notes', type=Path, nargs='+')
    parser.add_argument('--b-folder', type=Path)
    parser.add_argument('--adjudication', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'lock-b':
        require(bool(args.notes), 'B_NOTES_REQUIRED')
        print('B_REVIEWS_LOCKED', len(lock_b(args.notes, args.output)))
    elif args.action == 'prepare-adjudication':
        require(args.b_folder is not None, 'B_FOLDER_REQUIRED')
        _, _, _, conflicts = prepare_adjudication(args.b_folder, args.output)
        print('DISPUTES_REQUIRING_SOURCE_REVIEW', len(conflicts))
    else:
        require(args.b_folder is not None and args.adjudication is not None, 'B_AND_ADJUDICATION_REQUIRED')
        result = aggregate(args.b_folder, args.adjudication, args.output)
        print(result['status'], 'primary=', result['primary_outputs'], 'secondary=', result['secondary_outputs'])
