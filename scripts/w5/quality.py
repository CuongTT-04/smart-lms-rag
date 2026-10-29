"""Machine validation and explicit peer gates; no automatic semantic acceptance."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
from jsonschema import Draft202012Validator, FormatChecker
from .common import (content_hash, digest, normalize, projected, read_csv, read_json,
                     prompt_data_strings, sha_file, similarity, timestamp, within)
from apps.ai.providers.base import GenerationError


def _questions(value):
    if isinstance(value,list):
        for row in value: yield from _questions(row)
    elif isinstance(value,dict):
        if isinstance(value.get('question'),str) and value['question'].strip(): yield value['question']
        for key,item in value.items():
            if key!='question' and isinstance(item,(dict,list)): yield from _questions(item)


def _targets(value):
    if isinstance(value,list):
        for row in value:yield from _targets(row)
    elif isinstance(value,dict):
        for key,item in value.items():
            if key in ('ground_truth','ground_truth_reviewed','target_text') and isinstance(item,str) and len(normalize(item))>=80:yield item
            elif isinstance(item,(dict,list)):yield from _targets(item)


def benchmark_inputs(contract, root):
    hashes=set(); questions=set(); ids=set();target_hashes=set();targets=set()
    for item in contract['exclusion']['protected_inputs']:
        path=within(root,item['path'])
        # Existing exclusion hashes bind Git LF text; Windows checkouts use CRLF.
        if sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=item['sha256']: raise ValueError('Protected benchmark changed: '+item['path'])
        for row in item['records']:
            ids.add(row['record_id'])
            if row.get('question_sha256'): hashes.add(row['question_sha256'])
            if row.get('target_sha256'): target_hashes.add(row['target_sha256'])
        payload=read_csv(path) if path.suffix=='.csv' else read_json(path)
        questions.update(_questions(payload))
        targets.update(_targets(payload))
    return hashes,sorted(questions),ids,target_hashes,sorted(targets)


def verify_source(context, record, contract, root, cache):
    if record['source_identity_scope']=='fixture_only':
        source=contract['fixture']
        for key in ('document_id','version_id','source_checksum','page_number','text_sha256'):
            if context[key]!=source[key]: raise ValueError('Fixture identity mismatch')
        if context['text']!=source['text'] or context['rights_reference']!='FIXTURE:self-authored-w5': raise ValueError('Fixture text mismatch')
        return source['source_group_id']
    sources=[s for s in contract['sources']['sources'] if s['document_id']==context['document_id'] and s['version_id']==context['version_id']]
    if len(sources)!=1: raise ValueError('Unknown source identity')
    s=sources[0]
    if s['course_code']!=record['course_code'] or context['source_checksum']!=s['source_checksum']: raise ValueError('Source course/checksum mismatch')
    if (s.get('generation_authorized') is not True or not s.get('rights_evidence_reference')
        or context['rights_reference']!=s['rights_evidence_reference']): raise ValueError('Source permission not authorized')
    path=within(root,s['relative_path'])
    if path not in cache:
        from pypdf import PdfReader
        if sha_file(path)!=s['source_checksum']: raise ValueError('PDF checksum mismatch')
        reader=PdfReader(path)
        if len(reader.pages)!=s['page_count']: raise ValueError('PDF page count mismatch')
        cache[path]=reader
    reader=cache[path]; page=context['page_number']
    if not 1<=page<=len(reader.pages): raise ValueError('Page outside PDF')
    key=(path,page)
    if key not in cache: cache[key]=reader.pages[page-1].extract_text() or ''
    policy=contract['quality'].get('evidence_whitespace_policy','COLLAPSE')
    if policy=='NFC_REMOVE_WHITESPACE':
        from .group_candidate import source_excerpt_matches
        matched=source_excerpt_matches(cache[key],context['text'])
    elif policy=='COLLAPSE':matched=normalize(context['text']) in normalize(cache[key])
    else:raise ValueError('Unknown evidence whitespace policy')
    if not matched: raise ValueError('Excerpt is not on the cited physical page')
    allocations=[a for a in contract['allocation'] if a['source_group_id']==s['source_group_id']]
    if len(allocations)!=1 or allocations[0]['primary_author_member']!=record['author_member']: raise ValueError('Source assigned to another author')
    if not int(allocations[0]['page_start'])<=page<=int(allocations[0]['page_end']): raise ValueError('Page outside allocation')
    return s['source_group_id']


def check_review(record, reviews, policy):
    rows=[r for r in reviews if r.get('record_id')==record['record_id'] and r.get('content_sha256')==record['content_sha256']]
    if not rows: return False,'Missing peer review for current content hash'
    try:
        dated=[(timestamp(r['reviewed_at']),r) for r in rows]
        latest=max(d for d,_ in dated); matches=[r for d,r in dated if d==latest]
        if len(matches)!=1: return False,'Conflicting reviews at same timestamp'
        row=matches[0]
        if latest>datetime.now(timezone.utc) or latest<timestamp(record['provenance']['created_at']): return False,'Invalid review time'
        if row['reviewer_member']!={'A':'B','B':'A'}[record['author_member']]: return False,'Author cannot self-review'
        scores={k:int(row[k]) for k in policy['criteria']}
        if any(type(row[k]) is bool or str(row[k]) not in ('0','1','2') for k in scores): return False,'Invalid rubric scores'
        if row['decision']!='ACCEPT' or not str(row['reason']).strip(): return False,'Review is not ACCEPT with reason'
        if sum(scores.values())<policy['minimum_total'] or min(scores.values())==0 or any(scores[k]!=2 for k in policy['required_score_2']): return False,'Rubric threshold failed'
    except (KeyError,ValueError,TypeError): return False,'Malformed review'
    return True,None


def validate_records(records, contract, root, *, fixture_mode=False, reviews=(), stage='candidate', adjudications=()):
    if stage not in ('candidate','release'): raise ValueError('Unknown validation stage')
    if stage=='release' and not contract['approval'].get('locked'): raise ValueError('Contract not locked')
    if any(isinstance(r,dict) and r.get('source_identity_scope')=='offline_corpus' for r in records):
        from importlib.metadata import version
        if version('pypdf')!=contract['quality'].get('pdf_library_reference','pypdf==6.10.0').split('==')[1]:
            raise ValueError('PDF extraction library differs from pinned source verification runtime')
    validator=Draft202012Validator(contract['schema'],format_checker=FormatChecker())
    protected,protected_questions,protected_ids,protected_targets,target_texts=benchmark_inputs(contract,root)
    findings=[]; valid=[]; eligible=[]; cache={}; seen_ids=set(); questions={}; clean=[]; confirmed=[]
    row_map={r.get('record_id'):r for r in records if isinstance(r,dict)}
    def resolved(left, right, benchmark=False):
        other_id=sha256(normalize(right).encode()).hexdigest() if benchmark else right
        matches=[a for a in adjudications if a.get('record_id')==left['record_id'] and a.get('other_id')==other_id]
        if len(matches)!=1: return False
        a=matches[0]
        try:
            if a['content_sha256']!=left['content_sha256'] or a['reviewer_member'] not in ('A','B') or not a['reason'].strip(): return False
            if timestamp(a['reviewed_at'])>datetime.now(timezone.utc): return False
            if not benchmark and a['other_sha256']!=row_map[right]['content_sha256']: return False
            if benchmark and a['other_sha256']!=sha256(normalize(right).encode()).hexdigest(): return False
            if a['decision']=='DISTINCT': return True
            if a['decision']=='SAME_FAMILY' and not benchmark:
                confirmed.append(sorted([left['record_id'],right]));return True
        except (KeyError,TypeError,ValueError): return False
        return False
    def add(rid,code,detail,severity='ERROR',other=None):
        findings.append(dict(record_id=rid,code=code,detail=detail,severity=severity,other_id=other))
    for record in records:
        rid=record.get('record_id','<invalid>') if isinstance(record,dict) else '<invalid>'
        start=len(findings)
        errors=list(validator.iter_errors(record))
        if errors:
            add(rid,'SCHEMA','; '.join(sorted({e.validator for e in errors})));continue
        if rid in seen_ids: add(rid,'DUPLICATE_ID','Repeated record ID')
        seen_ids.add(rid)
        if content_hash(record)!=record['content_sha256']: add(rid,'CONTENT_HASH','Canonical content hash mismatch')
        if any(re.search(r'<\|[^<>\r\n]{1,80}\|>',s) for s in [*prompt_data_strings(record),record['target_text']]):
            add(rid,'SPECIAL_TOKEN','Model role/special token in untrusted training content')
        fixture=record['source_identity_scope']=='fixture_only'
        if fixture and (not fixture_mode or stage=='release'): add(rid,'FIXTURE','Fixture cannot enter real dataset/release')
        if not fixture:
            for source,value in [('record_id',rid),('parent_record_id',record['parent_record_id'])]:
                if value in protected_ids: add(rid,'BENCHMARK_EXACT','Protected benchmark identity in '+source)
        groups=set()
        for context in record['contexts']:
            if sha256(context['text'].encode()).hexdigest()!=context['text_sha256']: add(rid,'SOURCE','Text checksum mismatch')
            try: groups.add(verify_source(context,record,contract,root,cache))
            except (ValueError,OSError,KeyError) as exc: add(rid,'SOURCE',str(exc))
        if groups!=set(record['source_group_ids']): add(rid,'SOURCE_GROUP','Source groups do not match actual contexts')
        try:
            from apps.ai.rag.citations import parse_answer
            from apps.ai.rag.guardrails import parse_reading_hint
            contexts,_=projected(record,contract)
            if record['mode']=='qa' and record['exercise'] is not None: raise ValueError('QA cannot carry exercise context')
            if len({c.source_id for c in contexts})!=len(contexts) or len({(c.document_id,c.version_id,c.chunk_id) for c in contexts})!=len(contexts): raise ValueError('Duplicate evidence identity')
            target=record['target_text']
            if record['task_type']=='hint': parse_reading_hint(target,contexts)
            elif record['task_type']=='insufficient_evidence':
                if target!='INSUFFICIENT_EVIDENCE': raise ValueError('Invalid sentinel')
            else:
                status,_,_,_=parse_answer(target,contexts)
                if status!='ANSWERED': raise ValueError('Answer task requires cited answer')
        except (GenerationError,ValueError,TypeError,KeyError):
            # RAG GenerationError deliberately does not expose target text in reports.
            add(rid,'TARGET_FORMAT','Target/exercise/evidence does not satisfy the pinned prompt/parser contract')
        q=normalize(record['question']);qh=sha256(q.encode()).hexdigest()
        target=normalize(re.sub(r'\[[0-9]+\]','',record['target_text']))
        if len(target)>=80:
            if sha256(target.encode()).hexdigest() in protected_targets:
                add(rid,'BENCHMARK_TARGET_EXACT','Long protected answer reused; short common terms are excluded from this rule')
            else:
                for prior in target_texts:
                    if similarity(target,prior)>=contract['quality']['duplicate_detection']['flag_threshold'] and not resolved(record,prior,benchmark=True):
                        add(rid,'BENCHMARK_TARGET_NEAR','Possible protected-answer derivative; human adjudication required','REVIEW',sha256(normalize(prior).encode()).hexdigest())
        if qh in protected: add(rid,'BENCHMARK_EXACT','Protected normalized question')
        else:
            for p in protected_questions:
                if similarity(q,p)>=contract['quality']['duplicate_detection']['flag_threshold'] and not resolved(record,p,benchmark=True):
                    add(rid,'BENCHMARK_NEAR','Possible benchmark paraphrase; human adjudication required','REVIEW',sha256(normalize(p).encode()).hexdigest())
        if q in questions:
            add(rid,'EXACT_DUPLICATE','Normalized question duplicate',other=questions[q])
            add(questions[q],'EXACT_DUPLICATE','Normalized question duplicate',other=rid)
        else: questions[q]=rid
        reviewed,reason=check_review(record,reviews,contract['quality']['rubric'])
        if not reviewed and (stage=='release' or any(r.get('record_id')==rid for r in reviews)): add(rid,'REVIEW',reason)
        if len(findings)==start: valid.append(rid)
        clean.append((record,reviewed))
    for i,(left,_) in enumerate(clean):
        for right,_ in clean[i+1:]:
            if normalize(left['question'])!=normalize(right['question']) and similarity(left['question'],right['question'])>=contract['quality']['duplicate_detection']['flag_threshold'] and not (resolved(left,right['record_id']) or resolved(right,left['record_id'])):
                add(left['record_id'],'NEAR_DUPLICATE','Possible related question','REVIEW',right['record_id'])
                add(right['record_id'],'NEAR_DUPLICATE','Possible related question','REVIEW',left['record_id'])
            lt=normalize(re.sub(r'\[[0-9]+\]','',left['target_text']));rt=normalize(re.sub(r'\[[0-9]+\]','',right['target_text']))
            if min(len(lt),len(rt))>=80 and similarity(lt,rt)>=contract['quality']['duplicate_detection']['flag_threshold'] and not (resolved(left,right['record_id']) or resolved(right,left['record_id'])):
                add(left['record_id'],'TARGET_NEAR_DUPLICATE','Long target/pair overlap requires human adjudication','REVIEW',right['record_id'])
                add(right['record_id'],'TARGET_NEAR_DUPLICATE','Long target/pair overlap requires human adjudication','REVIEW',left['record_id'])
    blocked={f['record_id'] for f in findings}
    valid=[rid for rid in valid if rid not in {f['record_id'] for f in findings if f['severity']=='ERROR'}]
    eligible=[r['record_id'] for r,reviewed in clean if reviewed and r['record_id'] not in blocked and r['source_identity_scope']=='offline_corpus']
    if stage=='release':
        if len(eligible)!=contract['quality']['target_accepted_records']: add('<dataset>','QUOTA','Accepted record total differs from locked quota')
        for key, quotas in [('author_member',contract['quality']['target_per_author']),('course_code',contract['quality']['course_quota']),('task_type',contract['quality']['task_quota'])]:
            for value,total in quotas.items():
                if sum(r.get(key)==value for r in records if r.get('record_id') in eligible)!=total: add('<dataset>','QUOTA',f'{key}={value} count differs from locked quota')
        for member in contract['quality']['target_per_author']:
            for task,total in contract['quality']['per_author_task_quota'].items():
                if sum(r['author_member']==member and r['task_type']==task for r in records if r.get('record_id') in eligible)!=total: add('<dataset>','QUOTA',f'Author {member}/{task} differs from locked quota')
    return dict(schema_version='w5-quality-v1',contract_fingerprint=contract['fingerprint'],stage=stage,fixture_mode=fixture_mode,
        passed=not any(f['severity']=='ERROR' or stage=='release' and f['severity']=='REVIEW' for f in findings),
        record_count=len(records),dataset_fingerprint=digest({r['record_id']:r.get('content_sha256') for r in records if isinstance(r,dict) and 'record_id' in r}),
        valid_ids=sorted(set(valid)),eligible_ids=sorted(set(eligible)),findings=findings,confirmed_pairs=sorted({tuple(p) for p in confirmed}),
        semantic_review='REQUIRED_FROM_OPPOSITE_MEMBER',near_duplicate_method='character_5gram_jaccard; not semantic proof',
        counts_by_task={task:sum(r.get('task_type')==task for r in records) for task in contract['quality']['task_quota']})
