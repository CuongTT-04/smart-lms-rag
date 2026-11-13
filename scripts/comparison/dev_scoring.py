"""Blind paired dev assessment. Semantic decisions are explicit, never keyword grades."""
import argparse
from copy import deepcopy
from collections import Counter
import csv
import json
from pathlib import Path
import random
from zipfile import ZipFile

from scripts.comparison.protocol import digest, read_rows, write_json, write_rows
from scripts.qlora.data import loads, require, sha_file
from scripts.qlora.runtime import inventory

ROOT=Path(__file__).resolve().parents[2]


def prepare(output):
    require(not output.exists(),'NEW_REVIEW_DIRECTORY_REQUIRED')
    output.mkdir(parents=True)
    root=ROOT/'.private/comparison'
    reference=root/'inputs/v3/evaluator/dev/dev.references.jsonl'
    rubric=root/'inputs/v3/evaluator/dev/rubric.md'
    refs={r['qa_id']:r for r in read_rows(reference)}
    caches={r['qa_id']:r for r in read_rows(root/'prepared/retrieval-v2/dev.cache.jsonl')}
    cases, mapping, provenance = [],[],{}
    for label,archive in (('old',root/'prepared/training-runner-v3/baseline/dev-20261112T173555278014Z.zip'),
                          ('new',root/'runs/dev-20261112T203002043135Z.zip')):
        with ZipFile(archive) as zipped:
            rows=[json.loads(s) for s in zipped.read('outputs.jsonl').decode().splitlines()]
        tuned=[r for r in rows if r['arm']=='tuned_rag']
        require(len(tuned)==30 and {r['qa_id'] for r in tuned}==set(refs),'DEV_REVIEW_ID_SET')
        provenance[label]=dict(archive_sha256=sha_file(archive),run_id=tuned[0]['run_id'],
                               adapter_sha256=tuned[0]['adapter_sha256'])
        for row in tuned:
            ref=refs[row['qa_id']]
            cache=caches[row['qa_id']]
            require(row['contexts_sha256']==cache['contexts_sha256'],'DEV_REVIEW_CONTEXT_BINDING')
            evidence=[dict(evidence_id=f'E{i}.1',**c) for i,c in enumerate(cache['contexts'],1)]
            cases.append((label,row,dict(qa_id=ref['qa_id'],question=ref['question'],
                course_code=ref['course_code'],answerable=ref['answerable'],reference=ref['reference'],
                reference_sha256=digest(ref),raw_output=row['raw_output'],raw_output_sha256=digest(row['raw_output']),
                generation_status=row['status'],contexts=evidence)))
    random.Random(42).shuffle(cases)
    blinded=[]
    for index,(label,row,case) in enumerate(cases,1):
        blind_id=f'J{index:03}'
        blinded.append(dict(blind_id=blind_id,**case))
        mapping.append(dict(blind_id=blind_id,label=label,qa_id=row['qa_id'],run_id=row['run_id'],
                            output_record_sha256=digest(row),generation_seconds=row['generation_seconds'],output_tokens=row['output_tokens']))
    write_rows(output/'blinded.jsonl',blinded)
    write_rows(output/'mapping.PRIVATE.jsonl',mapping)
    write_json(output/'judge-config.json',dict(assessment_kind='AUTOMATED_RUBRIC',
        scope='60 tuned_rag outputs; paired 30 dev questions; not main scoring or independent peer approval',
        reviewer='CURRENT_ASSISTANT_SESSION',exact_model_revision=None,decoding_temperature=None,
        semantic_review_reproducibility='Exact model/revision/decoding not exposed. Explicit saved judgments are auditable; only validation and aggregation are deterministic.',
        blinding_seed=42,reference_sha256=sha_file(reference),rubric_sha256=sha_file(rubric),
        inputs=provenance,claims_policy='Split verifiable propositions within each item. Citation support is checked per claim against the cited full evidence text supplied to the model. No output repair.',
        correctness_policy='Score 2 for answering all demanded parts, 1 for meaningful partial answer, 0 for wrong material conclusion or false refusal. Extra correct but unasked elaboration in a broad reference is not mandatory.',
        abstention_policy='All 30 dev references are answerable; correct-abstention rate is N/A, false-abstention is measured.',
        independent_second_review=False))


def validate(case, review):
    require(review['blind_id']==case['blind_id'] and review['raw_output_sha256']==case['raw_output_sha256']
            and review['reference_sha256']==case['reference_sha256'],'JUDGMENT_BINDING')
    require(type(review['correctness']) is int and review['correctness'] in (0,1,2)
            and bool(review['reason']) and isinstance(review['missing_points'],list),'JUDGMENT_SCORE')
    value=loads(case['raw_output'])
    require(set(value)=={'items'} and isinstance(value['items'],list),'RAW_FORMAT_REVIEW_REQUIRED')
    require(all(isinstance(item,dict) and set(item)=={'text','evidence_id'}
                and isinstance(item['text'],str) and item['text'].strip()
                and isinstance(item['evidence_id'],str) for item in value['items']),'RAW_ITEM_REVIEW_REQUIRED')
    expected=set(range(len(value['items'])))
    require({c['item_index'] for c in review['claims']}==expected,'CLAIM_ITEM_COVERAGE')
    contexts={c['evidence_id']:c for c in case['contexts']}
    for claim in review['claims']:
        require(claim['status'] in ('supported','unsupported','contradicted') and bool(claim['claim']),'CLAIM_STATUS')
        item=value['items'][claim['item_index']]
        selected=contexts.get(item['evidence_id'])
        require(claim['citation_supported'] in (True,False),'CITATION_VERDICT')
        quote=claim.get('support_quote','')
        if claim['citation_supported']:
            require(claim['status']=='supported' and selected is not None and quote
                    and quote in selected['text'],'CITATION_SUPPORT_QUOTE')
        if claim['status']=='supported':
            require(any(quote and quote in c['text'] for c in case['contexts']),'FAITHFULNESS_SUPPORT_QUOTE')
        if claim['status']=='contradicted':
            require(any(claim.get('counter_quote') and claim['counter_quote'] in c['text'] for c in case['contexts']),'CONTRADICTION_QUOTE')
        require(bool(claim.get('reason')),'CLAIM_REASON')
    return value


def materialize(output):
    cases={r['blind_id']:r for r in read_rows(output/'blinded.jsonl')}
    notes=json.loads((output/'review-notes.json').read_text(encoding='utf-8'))
    require(set(notes)==set(cases),'NOTE_COMPLETENESS')
    require(not (output/'judgments.jsonl').exists(),'JUDGMENTS_ALREADY_LOCKED')
    records=[]
    for bid,case in cases.items():
        note=deepcopy(notes[bid])
        if 'same_as' in note:
            other=cases[note['same_as']]
            require(case['qa_id']==other['qa_id'] and case['raw_output_sha256']==other['raw_output_sha256']
                    and case['contexts']==other['contexts'],'SHARED_JUDGMENT_REQUIRES_IDENTICAL_INPUT_OUTPUT')
            note=deepcopy(notes[note['same_as']])
        sources={c['evidence_id']:c for c in case['contexts']}
        claims=[]
        for index,text,evidence,cited in note['claims']:
            status='contradicted' if evidence.startswith('contradicted:') else 'unsupported' if evidence=='unsupported' else 'supported'
            eid=evidence.split(':')[-1]
            source=sources.get(eid)
            claim=dict(item_index=index,claim=text,status=status,citation_supported=cited,
                reason=note['reason'],support_quote=source['text'] if source and status=='supported' else '',
                counter_quote=source['text'] if source and status=='contradicted' else '',
                source=None if source is None else {k:source[k] for k in ('evidence_id','document_id','version_id','page_number','char_start','char_end','source_checksum')})
            claims.append(claim)
        review=dict(blind_id=bid,raw_output_sha256=case['raw_output_sha256'],reference_sha256=case['reference_sha256'],
            correctness=note['score'],reason=note['reason'],missing_points=note['missing'],claims=claims)
        validate(case,review)
        records.append(review)
    write_rows(output/'judgments.jsonl',records)
    write_json(output/'judgments-lock.json',dict(judgments_sha256=sha_file(output/'judgments.jsonl'),
        review_notes_sha256=sha_file(output/'review-notes.json'),blinded_sha256=sha_file(output/'blinded.jsonl'),
        note='Judgments completed against blinded IDs before label aggregation. No independent second reviewer claimed.'))


def aggregate(output):
    cases={r['blind_id']:r for r in read_rows(output/'blinded.jsonl')}
    mapping={r['blind_id']:r for r in read_rows(output/'mapping.PRIVATE.jsonl')}
    reviews=read_rows(output/'judgments.jsonl')
    renderer={r['blind_id']:r for r in read_rows(output/'renderer.jsonl')}
    lock=json.loads((output/'judgments-lock.json').read_text(encoding='utf-8'))
    require(lock['judgments_sha256']==sha_file(output/'judgments.jsonl')
            and lock['review_notes_sha256']==sha_file(output/'review-notes.json')
            and lock['blinded_sha256']==sha_file(output/'blinded.jsonl'),'REVIEW_CHANGED_AFTER_LOCK')
    require(len(reviews)==60 and len({r['blind_id'] for r in reviews})==60
            and {r['blind_id'] for r in reviews}==set(cases),'REVIEW_COMPLETENESS')
    bylabel={'old':[],'new':[]}
    records=[]
    for review in reviews:
        case=cases[review['blind_id']]
        value=validate(case,review)
        render=renderer[review['blind_id']]
        require(render['raw_output_sha256']==case['raw_output_sha256']
                and render['status'] in ('RENDERED','BLOCKED'),'RENDERER_BINDING')
        row=dict(**mapping[review['blind_id']],course_code=case['course_code'],
            correctness=review['correctness'],false_abstention=not bool(value['items']),
            supported_claims=sum(c['status']=='supported' for c in review['claims']),
            claim_count=len(review['claims']),citation_pairs=len(review['claims']),
            supported_citation_pairs=sum(c['citation_supported'] for c in review['claims']),
            covered_claims=sum(c['citation_supported'] for c in review['claims']),
            raw_output_sha256=case['raw_output_sha256'],reason=review['reason'],
            json_parse_valid=True,
            item_text_format_valid=all(isinstance(item.get('text'),str) and '\n' not in item['text'] and '\r' not in item['text'] for item in value['items']),
            backend_renderable=render['status']=='RENDERED',
            displayed_correctness=review['correctness'] if render['status']=='RENDERED' else 0,
            citation_ids_valid=all(item.get('evidence_id') in {c['evidence_id'] for c in case['contexts']} for item in value['items']),
            missing_citations=sum(not item.get('evidence_id') for item in value['items']))
        bylabel[row['label']].append(row)
        records.append(row)
    def metrics(rows):
        n=len(rows)
        claims=sum(r['claim_count'] for r in rows)
        pairs=sum(r['citation_pairs'] for r in rows)
        return dict(cases=n,correctness_mean=sum(r['correctness'] for r in rows)/n,
            full_credit=sum(r['correctness']==2 for r in rows),partial=sum(r['correctness']==1 for r in rows),
            zero=sum(r['correctness']==0 for r in rows),correctness_percent=sum(r['correctness'] for r in rows)/(2*n)*100,
            false_abstentions=sum(r['false_abstention'] for r in rows),correct_abstention_rate=None,
            faithfulness_micro=sum(r['supported_claims'] for r in rows)/claims if claims else None,
            supported_claims=sum(r['supported_claims'] for r in rows),claims=claims,
            citation_precision_micro=sum(r['supported_citation_pairs'] for r in rows)/pairs if pairs else None,
            citation_coverage_micro=sum(r['covered_claims'] for r in rows)/claims if claims else None,
            citation_pairs=pairs,missing_citation_output_count=sum(r['missing_citations']>0 for r in rows),
            citation_ids_valid_outputs=sum(r['citation_ids_valid'] for r in rows),
            json_parse_valid_outputs=sum(r['json_parse_valid'] for r in rows),
            item_text_format_valid_outputs=sum(r['item_text_format_valid'] for r in rows),
            backend_renderable_outputs=sum(r['backend_renderable'] for r in rows),
            displayed_correctness_percent=sum(r['displayed_correctness'] for r in rows)/(2*n)*100,
            no_claim_output_count=sum(r['claim_count']==0 for r in rows),
            mean_generation_seconds=sum(r['generation_seconds'] for r in rows)/n,
            mean_output_tokens=sum(r['output_tokens'] for r in rows)/n)
    index={label:{r['qa_id']:r for r in rows} for label,rows in bylabel.items()}
    pairs=[]
    for rid in sorted(index['old']):
        left,right=index['old'][rid],index['new'][rid]
        pairs.append(dict(qa_id=rid,old=left['correctness'],new=right['correctness'],
                          delta=right['correctness']-left['correctness']))
    summary=dict(status='DEV_SEMANTIC_RUBRIC_REVIEW_COMPLETE',assessment_kind='AUTOMATED_RUBRIC',
        aggregate={label:metrics(rows) for label,rows in bylabel.items()},
        by_course={label:{course:metrics([r for r in rows if r['course_code']==course])
                         for course in sorted({r['course_code'] for r in rows})} for label,rows in bylabel.items()},
        paired=dict(wins=sum(p['delta']>0 for p in pairs),losses=sum(p['delta']<0 for p in pairs),
                    ties=sum(p['delta']==0 for p in pairs),correctness_total_delta=sum(p['delta'] for p in pairs)),
        correct_abstention='NOT_MEASURABLE_ALL_DEV_QUESTIONS_ANSWERABLE',
        limitations=['Development set reused for selection, not an independent unseen test.',
                    'One rubric review, not independent A/B agreement or locked external LLM judge API.',
                    'Faithfulness and citations use actual supplied context, not ID validity alone.',
                    'No evidence that a small difference is statistically significant.'],
        main_authorized=False)
    write_rows(output/'scored.jsonl',records)
    write_rows(output/'paired.jsonl',pairs)
    with (output/'scores.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    write_json(output/'summary.json',summary)
    write_json(output/'manifest.json',dict(scorer_sha256=sha_file(__file__),
        backend_renderer_sha256=sha_file(ROOT/'backend/apps/ai/rag/conversation.py'),
        files=inventory(output,('manifest.json',))))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','materialize','aggregate'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    {'prepare':prepare,'materialize':materialize,'aggregate':aggregate}[args.action](args.output)
