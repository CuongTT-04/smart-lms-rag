"""Blinded member-A main review and descriptive all-run metrics; never infer semantic scores from keywords."""
import argparse
from collections import Counter, defaultdict
import csv
from difflib import SequenceMatcher
import json
from pathlib import Path
import random
import re
import unicodedata

from scripts.comparison.protocol import digest, read_rows, write_json, write_rows
from scripts.qlora.data import loads, read_json, require, sha_file
from scripts.qlora.runtime import inventory

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / '.private/comparison'


def norm(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip()


def parse(raw):
    try:
        value = loads(raw)
    except (ValueError, TypeError):
        return dict(json_valid=False, schema_valid=False, items=[])
    valid = (isinstance(value, dict) and set(value) == {'items'} and isinstance(value['items'], list)
        and all(isinstance(i, dict) and set(i) == {'text','evidence_id'} and isinstance(i['text'], str)
                and i['text'].strip() and (i['evidence_id'] is None or isinstance(i['evidence_id'], str))
                for i in value['items']))
    return dict(json_valid=True, schema_valid=valid, items=value['items'] if valid else [])


def assignment(refs):
    groups = defaultdict(list)
    for row in refs:
        groups[row['course_code'], row['question_type']].append(row['qa_id'])
    roles = {}
    secondary = set()
    for (course, kind), ids in sorted(groups.items()):
        ids = sorted(ids)
        random.Random('42:' + course + ':' + kind).shuffle(ids)
        require(len(ids) % 2 == 0, 'MAIN_REVIEW_STRATUM_PARITY')
        for i, rid in enumerate(ids):
            roles[rid] = 'A' if i < len(ids)//2 else 'B'
        quota = 2 if kind == 'factual' else 1
        secondary.update(ids[len(ids)//2:len(ids)//2+quota])
    require(Counter(roles.values()) == {'A':150,'B':150} and len(secondary)==15, 'MAIN_REVIEW_QUOTA')
    return roles, secondary


def literal_support(text, contexts):
    # Textual identity establishes only source entailment, never answer correctness.
    needle = norm(text)
    return [eid for eid,c in contexts.items() if len(needle) >= 15 and needle in norm(c['text'])]


def prepare(output):
    require(not output.exists() and output.resolve().is_relative_to(ROOT / '.private'), 'NEW_MAIN_ASSESSMENT')
    refs = read_rows(DATA / 'prepared/benchmark-v3/main.references.jsonl')
    refmap = {r['qa_id']:r for r in refs}
    caches = {r['qa_id']:r for r in read_rows(DATA / 'prepared/retrieval-v2/main.cache.jsonl')}
    raw_path = DATA / 'runs/main-intake/main-20261113T011502419787Z/outputs.jsonl'
    raw = read_rows(raw_path)
    require(len(raw)==900 and len({(r['qa_id'],r['arm']) for r in raw})==900, 'MAIN_SCORING_RAW_COUNTS')
    roles, secondary = assignment(refs)
    shuffled = list(raw)
    random.Random(42).shuffle(shuffled)
    cases, mapping = [], []
    for i,row in enumerate(shuffled,1):
        ref = refmap[row['qa_id']]
        cache = caches[row['qa_id']]
        if row['arm'] != 'base':
            require(row['contexts_sha256']==cache['contexts_sha256'], 'MAIN_SCORER_CONTEXT_PIN')
        contexts = {f'E{j}.1':c for j,c in enumerate(cache['contexts'],1)} if row['arm'] != 'base' else {}
        bid = f'M{i:03}'
        parsed = parse(row['raw_output'])
        cases.append(dict(blind_id=bid, qa_id=row['qa_id'], question=ref['question'],
            course_code=ref['course_code'], question_type=ref['question_type'], answerable=ref['answerable'],
            content_sha256=ref['content_sha256'], reference=ref['reference'], reference_sha256=digest(ref),
            raw_output=row['raw_output'], raw_output_sha256=digest(row['raw_output']),
            generation_status=row['status'], contexts=contexts,
            parsed=parsed, literal_support=[literal_support(item['text'],contexts) for item in parsed['items']]))
        mapping.append(dict(blind_id=bid, qa_id=row['qa_id'], arm=row['arm'], primary_owner=roles[row['qa_id']],
            review_role='primary' if roles[row['qa_id']]=='A' else 'secondary' if row['qa_id'] in secondary else 'B_pending',
            run_id=row['run_id'], output_record_sha256=digest(row),
            generation_seconds=row['generation_seconds'], output_tokens=row['output_tokens'], input_tokens=row['input_tokens']))
    output.mkdir(parents=True)
    write_rows(output / 'blinded.jsonl',cases)
    write_rows(output / 'mapping.PRIVATE.jsonl',mapping)
    selected = {r['blind_id'] for r in mapping if r['review_role']!='B_pending'}
    packets = []
    for ref in refs:
        rows = [c for c in cases if c['qa_id']==ref['qa_id'] and c['blind_id'] in selected]
        if rows:
            packets.append(dict(packet=len(packets)+1,qa_id=ref['qa_id'], question=ref['question'],
                answerable=ref['answerable'],course=ref['course_code'],kind=ref['question_type'],
                required=ref['reference']['required_points'], outputs=rows))
    write_rows(output / 'review-packets.jsonl',packets)
    rubric = DATA / 'inputs/v3/evaluator/main/rubric.md'
    write_json(output / 'judge-config.json',dict(assessment_kind='AUTOMATED_RUBRIC',reviewer='A',
        rubric_sha256=sha_file(rubric), exact_model_revision=None, decoding_temperature=None,
        seed=42, primary=450, secondary=45, B_primary=450, B_secondary=45,
        engine='CURRENT_SESSION_SOURCE_GROUNDED_REVIEW_NOT_EXTERNAL_JUDGE_API',
        claim_unit='STRUCTURED_ITEM_CONSERVATIVE_ALL_SUBCLAIMS_REQUIRED',
        independent_AB_agreement='PENDING_B_REVIEW',
        failure_policy='Main correctness zero for noncompleted generation; raw content reviewed separately.',
        locked_raw_sha256=sha_file(raw_path), references_sha256=sha_file(DATA / 'prepared/benchmark-v3/main.references.jsonl'),
        prompt='Read question, required points, full source and actual contexts; grade semantic meaning 0/1/2. '
            'Empty answerable=0, valid insufficient abstention=2. Citation IDs alone never prove entailment. '
            'Keep raw format and generation failures independent. Do not repair or reward verbosity.'))


def show(output, start, stop):
    for packet in read_rows(output / 'review-packets.jsonl')[start-1:stop]:
        print('\nP'+str(packet['packet']),packet['course'],packet['kind'],packet['question'])
        print('GOLD',json.dumps(packet['required'],ensure_ascii=False))
        for row in packet['outputs']:
            items = row['parsed']['items']
            print(row['blind_id'],row['generation_status'],
                json.dumps([dict(i=i,text=item['text'],cite=item['evidence_id'],literal=row['literal_support'][i])
                            for i,item in enumerate(items)],ensure_ascii=False) if row['parsed']['schema_valid'] else row['raw_output'])


def concordance(output, start, stop):
    for packet in read_rows(output / 'review-packets.jsonl')[start-1:stop]:
        print('\nP'+str(packet['packet']))
        seen=set()
        for row in packet['outputs']:
            for i,item in enumerate(row['parsed']['items']):
                if row['literal_support'][i] or not row['contexts']:
                    continue
                needle=norm(item['text'])
                matches=[]
                for eid,context in row['contexts'].items():
                    text=norm(context['text'])
                    match=SequenceMatcher(None,needle,text,autojunk=False).find_longest_match()
                    matches.append((match.size,eid,text,max(0,match.b-140),min(len(text),match.b+match.size+230)))
                matches.sort(reverse=True)
                cited=item['evidence_id']
                picks=[x for x in matches if x[1]==cited]+matches[:1]
                for _,eid,text,left,right in picks:
                    key=(row['blind_id'],i,eid)
                    if key not in seen:
                        print(row['blind_id'],i,eid,'CITED' if eid==cited else 'OTHER',text[left:right])
                        seen.add(key)


def verify_sources(output):
    from pypdf import PdfReader
    registry=read_json(DATA / 'inputs/v3/evaluator/main/source-manifest.json')
    readers={}
    sources={r['document_id']:r for r in registry['sources']}
    pages={}
    def page(info):
        source=sources[info['document_id']]
        require(source['source_checksum']==info['source_checksum'] and source['version_id']==info['version_id'], 'SCORING_SOURCE_ID')
        key=source['document_id'], info['page_number']
        if key not in pages:
            if key[0] not in readers:
                pdf=ROOT / source['relative_path']
                require(sha_file(pdf)==source['source_checksum'], 'SCORING_PDF_CHECKSUM')
                readers[key[0]]=PdfReader(pdf)
            pages[key]=unicodedata.normalize('NFC',(readers[key[0]].pages[key[1]-1].extract_text() or '').replace('\r\n','\n').replace('\r','\n'))
        return pages[key]
    contexts=0
    for cache in read_rows(DATA / 'prepared/retrieval-v2/main.cache.jsonl'):
        for c in cache['contexts']:
            text=page(c)
            require(text[c['char_start']:c.get('packed_char_end',c['char_end'])]==c['text'], 'SCORING_CONTEXT_SPAN')
            contexts+=1
    gold=0
    for ref in read_rows(DATA / 'prepared/benchmark-v3/main.references.jsonl'):
        for evidence in ref['reference']['evidence']:
            require(page(evidence)==unicodedata.normalize('NFC',evidence['supporting_page_text']), 'SCORING_GOLD_PAGE')
            gold+=1
    write_json(output / 'source-verification.json',dict(status='ACTUAL_PDF_GOLD_AND_CONTEXT_BINDINGS_PASSED',
        context_bindings=contexts,gold_page_bindings=gold,pdfs=len(readers),physical_pages=len(pages),
        insufficient_scope_review= 'INHERITS_PRE_FREEZE_60_CASE_SCOPE_REVIEW_NOT_RELABELED_FROM_RETRIEVAL'))


def materialize(output):
    notes=read_json(output / 'review-notes.json')
    packets=read_rows(output / 'review-packets.jsonl')
    require(set(notes)=={str(p['packet']) for p in packets}, 'MAIN_NOTES_COMPLETENESS')
    require(not (output / 'reviews-a.jsonl').exists(), 'MAIN_REVIEWS_ALREADY_LOCKED')
    reviews=[]
    pending=[]
    for packet in packets:
        entries=notes[str(packet['packet'])]
        require(len(entries)==3, 'MAIN_PACKET_REVIEW_COUNT')
        for case,note in zip(packet['outputs'],entries):
            score,reason=note[:2]
            require(type(score) is int and score in (0,1,2) and reason, 'MAIN_SEMANTIC_SCORE')
            items=case['parsed']['items']
            statuses=note[2] if len(note)>2 else ['=']*len(items)
            require(len(statuses)==len(items), 'MAIN_ITEM_REVIEW_COUNT:'+case['blind_id'])
            claims=[]
            if case['contexts']:
                for i,(item,verdict) in enumerate(zip(items,statuses)):
                    if verdict=='n':
                        claims.append(dict(item_index=i,claim=item['text'],status='nonassertion',
                            citation_supported=False,sources=[],reason='Question echo, not a factual assertion.'))
                        continue
                    if verdict=='=':
                        ids=case['literal_support'][i]
                        if not ids:
                            pending.append(case['blind_id']+':'+str(i))
                            continue
                        ids=[item['evidence_id']] if item['evidence_id'] in ids else ids[:1]
                    else:
                        ids=[] if verdict=='u' else verdict.lstrip('!').split('+')
                    require(all(eid in case['contexts'] for eid in ids), 'MAIN_CLAIM_SOURCE_ID:'+case['blind_id'])
                    status='contradicted' if verdict.startswith('!') else 'supported' if ids else 'unsupported'
                    sources=[dict(evidence_id=eid,quote=case['contexts'][eid]['text'],
                        **{k:case['contexts'][eid][k] for k in ('document_id','version_id','page_number','char_start','char_end','source_checksum')}) for eid in ids]
                    claims.append(dict(item_index=i,claim=item['text'],status=status,sources=sources,
                        citation_supported=status=='supported' and ids==[item['evidence_id']],
                        citation_id=item['evidence_id'],reason=reason,
                        method='VERBATIM_SOURCE_IDENTITY_REVIEWED' if verdict=='=' else 'SEMANTIC_CONTEXT_REVIEW'))
            primary_score=score if case['generation_status']=='completed' else 0
            if not case['answerable'] and not case['parsed']['schema_valid']:
                primary_score=0
            reviews.append(dict(blind_id=case['blind_id'],qa_id=case['qa_id'],
                raw_output_sha256=case['raw_output_sha256'],reference_sha256=case['reference_sha256'],
                content_sha256=case['content_sha256'],correctness=primary_score,raw_content_score=score,
                reason=reason,required_points=case['reference']['required_points'],
                required_points_review='CORE_QUESTION_SATISFIED_SEE_RATIONALE' if score==2 else 'PARTIAL_OR_MISSING_SEE_RATIONALE',
                claims=claims,reviewer='A',assessment_kind='AUTOMATED_RUBRIC'))
    require(not pending,'MAIN_NONLITERAL_REVIEW_REQUIRED:'+','.join(pending))
    require(len(reviews)==495 and len({r['blind_id'] for r in reviews})==495,'MAIN_A_REVIEW_COUNT')
    write_rows(output / 'reviews-a.jsonl',reviews)
    write_json(output / 'reviews-lock.json',dict(reviews_sha256=sha_file(output/'reviews-a.jsonl'),
        notes_sha256=sha_file(output/'review-notes.json'),blinded_sha256=sha_file(output/'blinded.jsonl'),
        judge_config_sha256=sha_file(output/'judge-config.json'),
        note='Member A 450 primary + 45 secondary, no B approval/independent agreement asserted.'))


def renderer(output):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0,str(ROOT/'backend'))
    from apps.ai.rag.conversation import render_structured_answer
    records=[]
    for case in read_rows(output/'blinded.jsonl'):
        parsed=case['parsed']
        grounded=bool(case['contexts'])
        if grounded:
            contexts=[SimpleNamespace(text=c['text']) for c in case['contexts'].values()]
            try:
                rendered=render_structured_answer(case['raw_output'],contexts,require_proof=True)
                status='RENDERED'
                error=None
            except Exception as exc:
                status='BLOCKED';rendered=None
                error=getattr(exc,'validation_reason',type(exc).__name__)
        else:
            # Closed-book protocol permits evidence_id=null; do not apply grounded proof requirements.
            valid=parsed['schema_valid'] and len(parsed['items'])<=24 and all(
                item['evidence_id'] is None and '\n' not in item['text'] and '\r' not in item['text']
                for item in parsed['items'])
            status='PROTOCOL_VALID' if valid else 'PROTOCOL_INVALID'
            error=None if valid else 'BASE_PROTOCOL_INVALID'
            rendered=None
        records.append(dict(blind_id=case['blind_id'],raw_output_sha256=case['raw_output_sha256'],
            status=status,error=error,rendered=rendered,backend_renderer_applied=grounded))
    write_rows(output/'renderer.jsonl',records)


def quantile(values,p):
    values=sorted(values)
    if not values:return None
    pos=(len(values)-1)*p
    left=int(pos);right=min(left+1,len(values)-1)
    return values[left]+(values[right]-values[left])*(pos-left)


def semantic_metrics(rows):
    n=len(rows)
    claims=[c for r in rows for c in r['claims'] if c['status']!='nonassertion']
    pairs=[c for c in claims if c.get('citation_id')]
    supported=sum(c['status']=='supported' for c in claims)
    cited=sum(c['citation_supported'] for c in pairs)
    answerable=[r for r in rows if r['answerable']]
    insufficient=[r for r in rows if not r['answerable']]
    return dict(outputs=n,correctness_total=sum(r['correctness'] for r in rows),maximum=2*n,
        correctness_percent=100*sum(r['correctness'] for r in rows)/(2*n) if n else None,
        full_credit=sum(r['correctness']==2 for r in rows),partial=sum(r['correctness']==1 for r in rows),
        zero=sum(r['correctness']==0 for r in rows),answerable_outputs=len(answerable),
        answerable_correctness_percent=100*sum(r['correctness'] for r in answerable)/(2*len(answerable)) if answerable else None,
        insufficient_outputs=len(insufficient),correct_abstentions=sum(r['correctness']==2 for r in insufficient),
        correct_abstention_rate=sum(r['correctness']==2 for r in insufficient)/len(insufficient) if insufficient else None,
        false_protocol_abstentions=sum(r['protocol_abstention'] for r in answerable),
        faithfulness_item_micro=supported/len(claims) if claims else None,
        supported_items=supported,eligible_assertion_items=len(claims),
        citation_precision_item_micro=cited/len(pairs) if pairs else None,
        citation_coverage_item_micro=cited/len(claims) if claims else None,
        citation_attempt_items=len(pairs),supported_citation_items=cited,
        no_assertion_outputs=sum(not any(c['status']!='nonassertion' for c in r['claims']) for r in rows),
        raw_invalid_format_outputs=sum(not r['schema_valid'] for r in rows),
        displayed_correctness_percent=100*sum(r['displayed_correctness'] for r in rows)/(2*n) if n else None)


def paired(rows,left,right):
    import numpy as np
    lookup={(r['qa_id'],r['arm']):r for r in rows}
    ids=sorted({r['qa_id'] for r in rows})
    pairs=[dict(qa_id=rid,left=lookup[rid,left]['correctness'],right=lookup[rid,right]['correctness'],
        delta=lookup[rid,right]['correctness']-lookup[rid,left]['correctness']) for rid in ids]
    deltas=np.array([p['delta'] for p in pairs],dtype=float)
    rng=np.random.default_rng(42)
    values=deltas[rng.integers(0,len(ids),size=(10000,len(ids)))].mean(axis=1)/2*100
    return dict(left=left,right=right,questions=len(ids),wins=sum(p['delta']>0 for p in pairs),
        losses=sum(p['delta']<0 for p in pairs),ties=sum(p['delta']==0 for p in pairs),
        correctness_delta_percentage_points=float(deltas.mean()/2*100),
        paired_case_bootstrap_95_ci=[float(v) for v in np.quantile(values,[.025,.975])],
        bootstrap_resamples=10000,seed=42,pairs=pairs)


def aggregate(output):
    lock=read_json(output/'reviews-lock.json')
    for name,key in (('reviews-a.jsonl','reviews_sha256'),('review-notes.json','notes_sha256'),
                     ('blinded.jsonl','blinded_sha256'),('judge-config.json','judge_config_sha256')):
        require(sha_file(output/name)==lock[key],'MAIN_REVIEW_LOCK_CHANGED')
    cases={r['blind_id']:r for r in read_rows(output/'blinded.jsonl')}
    mapping={r['blind_id']:r for r in read_rows(output/'mapping.PRIVATE.jsonl')}
    judge=read_json(output/'judge-config.json')
    raw_path=DATA/'runs/main-intake/main-20261113T011502419787Z/outputs.jsonl'
    refs_path=DATA/'prepared/benchmark-v3/main.references.jsonl'
    require(sha_file(raw_path)==judge['locked_raw_sha256'] and
            sha_file(refs_path)==judge['references_sha256'],'MAIN_SCORER_RAW_OR_GOLD_CHANGED')
    raw=read_rows(raw_path)
    random.Random(42).shuffle(raw)
    owners,secondary_ids=assignment(read_rows(refs_path))
    require(set(mapping)==set(cases)=={f'M{i:03}' for i in range(1,901)},'MAIN_MAPPING_COVERAGE')
    for i,row in enumerate(raw,1):
        bid=f'M{i:03}';meta=mapping[bid];case=cases[bid]
        require(meta['arm']==row['arm'] and meta['qa_id']==case['qa_id']==row['qa_id'] and
                meta['output_record_sha256']==digest(row) and case['raw_output_sha256']==digest(row['raw_output']) and
                meta['generation_seconds']==row['generation_seconds'] and meta['output_tokens']==row['output_tokens'],
                'MAIN_BLIND_MAPPING_CHANGED')
        role='primary' if owners[row['qa_id']]=='A' else 'secondary' if row['qa_id'] in secondary_ids else 'B_pending'
        require(meta['primary_owner']==owners[row['qa_id']] and meta['review_role']==role,'MAIN_ASSIGNMENT_CHANGED')
    renders={r['blind_id']:r for r in read_rows(output/'renderer.jsonl')}
    records=[]
    for review in read_rows(output/'reviews-a.jsonl'):
        case=cases[review['blind_id']];meta=mapping[review['blind_id']];render=renders[review['blind_id']]
        require(review['raw_output_sha256']==case['raw_output_sha256']==render['raw_output_sha256'] and
                review['reference_sha256']==case['reference_sha256'],'MAIN_REVIEW_BINDING')
        record=dict(**review,arm=meta['arm'],review_role=meta['review_role'],course_code=case['course_code'],
            question_type=case['question_type'],answerable=case['answerable'],schema_valid=case['parsed']['schema_valid'],
            protocol_abstention=case['parsed']['schema_valid'] and not case['parsed']['items'],
            generation_status=case['generation_status'],generation_seconds=meta['generation_seconds'],
            render_status=render['status'],displayed_correctness=review['correctness'] if render['status'] in ('RENDERED','PROTOCOL_VALID') else 0)
        records.append(record)
    primary=[r for r in records if r['review_role']=='primary']
    secondary=[r for r in records if r['review_role']=='secondary']
    require(len(primary)==450 and len(secondary)==45,'MAIN_REVIEW_ROLES')
    arms=('base','rag','tuned_rag')
    metrics={a:semantic_metrics([r for r in primary if r['arm']==a]) for a in arms}
    all_run={}
    for arm in arms:
        meta=[m for m in mapping.values() if m['arm']==arm]
        cs=[cases[m['blind_id']] for m in meta]
        all_run[arm]=dict(outputs=len(cs),status_counts=dict(Counter(c['generation_status'] for c in cs)),
            raw_json_valid=sum(c['parsed']['json_valid'] for c in cs),schema_valid=sum(c['parsed']['schema_valid'] for c in cs),
            renderer_or_base_protocol_valid=sum(renders[c['blind_id']]['status'] in ('RENDERED','PROTOCOL_VALID') for c in cs),
            backend_renderer_eligible=arm!='base',protocol_abstentions=sum(c['parsed']['schema_valid'] and not c['parsed']['items'] for c in cs),
            generation_mean_seconds=sum(m['generation_seconds'] for m in meta)/len(meta),
            generation_p50_seconds=quantile([m['generation_seconds'] for m in meta],.5),
            generation_p95_seconds=quantile([m['generation_seconds'] for m in meta],.95),
            input_tokens=sum(m['input_tokens'] for m in meta),output_tokens=sum(m['output_tokens'] for m in meta))
    comparisons=[paired(primary,l,r) for l,r in (('base','rag'),('rag','tuned_rag'),('base','tuned_rag'))]
    summary=dict(status='MEMBER_A_450_PRIMARY_45_SECONDARY_COMPLETE_GROUP_SCORING_PENDING',
        assessment_kind='AUTOMATED_RUBRIC',primary_outputs=450,primary_questions=150,secondary_outputs=45,
        primary_metrics=metrics,all_900_technical_metrics=all_run,
        secondary_metrics={a:semantic_metrics([r for r in secondary if r['arm']==a]) for a in arms},
        by_course={course:{a:semantic_metrics([r for r in primary if r['arm']==a and r['course_code']==course]) for a in arms}
            for course in ('CNXHKH','KTCTMLN','THMLN')},
        by_type={kind:{a:semantic_metrics([r for r in primary if r['arm']==a and r['question_type']==kind]) for a in arms}
            for kind in ('factual','explanation','multi_page','insufficient')},
        paired=[{k:v for k,v in c.items() if k!='pairs'} for c in comparisons],
        limitations=['Semantic scores cover A primary 150 of 300 questions, not all 900 outputs.',
            '45 secondary outputs are separate, not added to primary denominators; B reviews/adjudication pending.',
            'Single current-session rubric reviewer; exact platform model revision unavailable, not an external pinned API judge.',
            'Faithfulness/citations use conservative structured-item units; compound items need all subclaims supported. Not atomic-claim estimates.',
            'Faithfulness/citation exclude unparseable raw items and empty/nonassertion outputs; report these counts, not assume full support.',
            'Base faithfulness/citation N/A; Base protocol checker is not grounded backend renderer.',
            'Benchmark has disclosed partial conceptual overlap; do not claim fully novel generalization.'])
    write_rows(output/'scored-a.jsonl',records)
    write_json(output/'summary.json',summary)
    write_json(output/'paired.json',comparisons)
    with (output/'metrics.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['scope','arm',*next(iter(metrics.values())).keys()])
        writer.writeheader();writer.writerows(dict(scope='A_PRIMARY_150_QUESTIONS_PER_ARM',arm=a,**metrics[a]) for a in arms)
    errors=[dict(blind_id=r['blind_id'],qa_id=r['qa_id'],arm=r['arm'],review_role=r['review_role'],
        course=r['course_code'],question_type=r['question_type'],score=r['correctness'],reason=r['reason'],
        generation_status=r['generation_status'],render_status=r['render_status']) for r in records
        if r['correctness']<2 or r['render_status'] not in ('RENDERED','PROTOCOL_VALID')]
    with (output/'errors.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(errors[0]));writer.writeheader();writer.writerows(errors)
    write_rows(output/'reviews-b-assignment.PRIVATE.jsonl',[dict(**mapping[c['blind_id']],**{k:c[k] for k in
        ('question','course_code','question_type','reference_sha256','raw_output_sha256')}) for c in cases.values()
        if mapping[c['blind_id']]['primary_owner']=='B'])
    write_json(output/'manifest.json',dict(scorer_sha256=sha_file(__file__),files=inventory(output,('manifest.json',))))
    print(json.dumps({a:{k:v for k,v in m.items() if k in ('correctness_total','maximum','correctness_percent','correct_abstention_rate','false_protocol_abstentions','faithfulness_item_micro','citation_precision_item_micro','citation_coverage_item_micro')} for a,m in metrics.items()},indent=2))


def finish(output):
    import math
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    summary=read_json(output/'summary.json')
    refs=read_rows(DATA/'prepared/benchmark-v3/main.references.jsonl')
    caches={r['qa_id']:r for r in read_rows(DATA/'prepared/retrieval-v2/main.cache.jsonl')}
    scores=[]
    for ref in refs:
        if not ref['answerable']:continue
        gold={(e['document_id'],e['version_id'],e['page_number']) for e in ref['reference']['evidence']}
        retrieved=list(dict.fromkeys((c['document_id'],c['version_id'],c['page_number']) for c in caches[ref['qa_id']]['contexts']))
        hits=[int(p in gold) for p in retrieved]
        ideal=sum(1/math.log2(i+2) for i in range(min(5,len(gold))))
        scores.append(dict(qa_id=ref['qa_id'],course=ref['course_code'],kind=ref['question_type'],
            gold_pages=len(gold),retrieved_unique_pages=len(retrieved),
            recall_at_5=len(gold & set(retrieved))/len(gold),
            reciprocal_rank_at_5=next((1/(i+1) for i,v in enumerate(hits) if v),0),
            ndcg_at_5=sum(v/math.log2(i+2) for i,v in enumerate(hits))/ideal,
            all_gold_pages_retrieved=gold.issubset(set(retrieved))))
    retrieval=dict(eligible_questions=len(scores),insufficient_excluded=60,
        page_recall_at_5=sum(r['recall_at_5'] for r in scores)/len(scores),
        page_mrr_at_5=sum(r['reciprocal_rank_at_5'] for r in scores)/len(scores),
        page_ndcg_at_5=sum(r['ndcg_at_5'] for r in scores)/len(scores),
        multi_page_all_gold_recall=sum(r['all_gold_pages_retrieved'] for r in scores if r['kind']=='multi_page')/
            sum(r['kind']=='multi_page' for r in scores),
        ranking='Deduplicate physical pages in the frozen top-5 chunks, without refilling; binary page relevance.',
        shared_by_rag_and_tuned=True)
    write_rows(output/'retrieval-scores.jsonl',scores)
    write_json(output/'retrieval-summary.json',retrieval)
    cases=read_rows(output/'blinded.jsonl')
    mapping={r['blind_id']:r for r in read_rows(output/'mapping.PRIVATE.jsonl')}
    owner, _=assignment(refs)
    bsecondary=set()
    for course in ('CNXHKH','KTCTMLN','THMLN'):
        for kind in ('factual','explanation','multi_page','insufficient'):
            ids=sorted(r['qa_id'] for r in refs if owner[r['qa_id']]=='A' and r['course_code']==course and r['question_type']==kind)
            random.Random('42:Bsecondary:'+course+':'+kind).shuffle(ids)
            bsecondary.update(ids[:2 if kind=='factual' else 1])
    selected=[c for c in cases if owner[c['qa_id']]=='B' or c['qa_id'] in bsecondary]
    require(len(selected)==495,'B_HANDOFF_REVIEW_COUNTS')
    write_rows(output/'blinded-b.jsonl',selected)
    write_rows(output/'reviews-b-assignment.PRIVATE.jsonl',[
        dict(**mapping[c['blind_id']],b_review_role='primary' if owner[c['qa_id']]=='B' else 'secondary') for c in selected])
    write_json(output/'group-status.json',dict(A_primary_completed=450,A_secondary_completed=45,
        B_primary_completed=0,B_secondary_completed=0,B_assigned_primary=450,B_assigned_secondary=45,
        independent_agreement=None,adjudication='PENDING_INDEPENDENT_B_REVIEWS',
        all_900_semantic_scores_available=False))
    figures=output/'figures';figures.mkdir(exist_ok=True)
    labels=['Base','RAG','Tuned + RAG'];arms=['base','rag','tuned_rag']
    for name,title,values,ylabel in (
        ('correctness.png','Primary Review: 150 Questions per Arm',
         [summary['primary_metrics'][a]['correctness_percent'] for a in arms],'Correctness score (%)'),
        ('latency.png','Main Generation: 300 Questions per Arm',
         [summary['all_900_technical_metrics'][a]['generation_mean_seconds'] for a in arms],'Mean generation time (s)')):
        fig,ax=plt.subplots(figsize=(9,4.8),layout='constrained')
        bars=ax.bar(labels,values,color=['#777777','#267b65','#bc5264'],width=.55)
        ax.bar_label(bars,fmt='%.2f',padding=4)
        ax.set(title=title,ylabel=ylabel,ylim=(0,100 if name=='correctness.png' else max(values)*1.25))
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
        fig.savefig(figures/name,dpi=180);plt.close(fig)
    state_path=DATA/'experiment-readiness.json'
    state=read_json(state_path)
    state.update(status='STEP8_MEMBER_A_COMPLETE_GROUP_B_REVIEW_AND_ADJUDICATION_NEXT',
        main_semantic_scoring='A_450_PRIMARY_45_SECONDARY_COMPLETE_NOT_FULL_GROUP',
        main_assessment_path=output.relative_to(ROOT).as_posix(),
        A_primary_review_count=450,A_secondary_review_count=45,
        B_review_status='PENDING',main_group_adjudication='PENDING',
        chatbot_adapter_changed=False)
    write_json(state_path,state)
    write_json(output/'manifest.json',dict(scorer_sha256=sha_file(__file__),
        backend_renderer_sha256=sha_file(ROOT/'backend/apps/ai/rag/conversation.py'),
        files=inventory(output,('manifest.json',))))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','show','concordance','verify-sources','materialize','renderer','aggregate','finish'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--start',type=int,default=1)
    parser.add_argument('--stop',type=int,default=10)
    args=parser.parse_args()
    if args.action=='prepare': prepare(args.output)
    elif args.action=='materialize': materialize(args.output)
    elif args.action=='renderer': renderer(args.output)
    elif args.action=='aggregate': aggregate(args.output)
    elif args.action=='finish': finish(args.output)
    elif args.action=='verify-sources': verify_sources(args.output)
    elif args.action=='concordance': concordance(args.output,args.start,args.stop)
    else: show(args.output,args.start,args.stop)
