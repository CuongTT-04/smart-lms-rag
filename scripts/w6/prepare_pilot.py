"""Convert explicit W5 citations to W6 IDs without inventing source assignments."""
import hashlib
import json
import re
import sys
from collections import Counter, deque
from pathlib import Path

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.w6.contracts import ROOT,canonical,digest,loads,require,validate_payload
if str(ROOT/'backend') not in sys.path:sys.path.insert(0,str(ROOT/'backend'))
from apps.ai.rag.base import EvidenceContext
from apps.ai.rag.conversation import FORMAT_REPAIR_INSTRUCTION,build_evidence_units,render_structured_answer
from apps.ai.rag.guardrails import check_request_policy,parse_reading_hint


def convert_row(row,metadata):
    user=validate_payload(row);task=metadata['task_type'];target=row['completion'][0]['content']
    untrusted=json.dumps(user,ensure_ascii=False)+target
    require(not re.search(r'<\|[^<>\r\n]{1,80}\|>',untrusted),'SPECIAL_TOKEN_IN_DATA')
    check_request_policy(user['question'])
    contexts=[EvidenceContext.from_value({k:v for k,v in ctx.items() if k!='citation_label'}) for ctx in user['evidence']]
    units=build_evidence_units(contexts);mapping=[]
    if task=='hint':
        require(user['mode']=='hint','TASK_MODE');parse_reading_hint(target,contexts)
        result=json.loads(json.dumps(row))
    else:
        require(user['mode']=='qa' and user['exercise'] is None,'TASK_MODE')
        if task=='insufficient_evidence':
            require(target=='INSUFFICIENT_EVIDENCE','REFUSAL_TARGET');items=[]
        else:
            require('INSUFFICIENT_EVIDENCE' not in target,'MIXED_TARGET')
            matches=list(re.finditer(r'(?:\[[1-9][0-9]*\][ \t]*)+',target))
            require(matches,'UNCITED_TEXT');items=[];previous=0
            compact=lambda value:''.join(value.split()).strip('.;')
            for match in matches:
                claim=target[previous:match.start()].strip().lstrip('.;').strip()
                labels=list(dict.fromkeys(int(n) for n in re.findall(r'\[([0-9]+)\]',match[0])))
                require(claim and all(1<=n<=len(contexts) for n in labels),'UNKNOWN_SOURCE')
                candidates=[u for u in units if u['citation_label'] in labels]
                if len(labels)==1 and len(candidates)==1:
                    chosen=candidates[0];method='EXPLICIT_LABEL_SINGLE_UNIT'
                else:
                    exact=[u for u in candidates if compact(claim) in compact(u['text'])]
                    require(len(exact)==1,'AMBIGUOUS_EVIDENCE');chosen=exact[0];method='EXACT_TEXT_WITHIN_DECLARED_SOURCES'
                items.append({'text':claim,'evidence_id':chosen['evidence_id']})
                mapping.append({'claim_index':len(items)-1,'old_labels':labels,'evidence_id':chosen['evidence_id'],
                                'source_id':contexts[chosen['citation_label']-1].source_id,'method':method})
                previous=match.end()
            require(not target[previous:].strip(' .;\r\n\t'),'UNCITED_TEXT')
        new_user={**user,'evidence':units}
        result={'prompt':[{'role':'system','content':FORMAT_REPAIR_INSTRUCTION},
                          {'role':'user','content':json.dumps(new_user,ensure_ascii=False)}],
                'completion':[{'role':'assistant','content':json.dumps({'items':items},ensure_ascii=False,separators=(',',':'))}]}
        render_structured_answer(result['completion'][0]['content'],contexts,require_proof=True)
    m=dict(source_record_id=metadata['record_id'],source_content_sha256=metadata['content_sha256'],
           source_sft_sha256=metadata['sft_sha256'],training_payload_sha256=digest(result),
           split=metadata['split'],source_row_index=metadata['row_index'],author_member=metadata['author_member'],course_code=metadata['course_code'],
           task_type=task,source_group_ids=metadata['source_group_ids'],variant_family_id=metadata['variant_family_id'],
           source_identity_scope=metadata['source_identity_scope'],sources=metadata['sources'],
           conversion_version='w6-explicit-evidence-v1',semantic_peer_review='NOT_ASSERTED',
           original_target_preserved_except_protocol=True)
    return {'payload':result,'metadata':m,'mapping':mapping}


def select_records(rows,course_quotas,task_quotas,seed):
    """Integer flow gives both margins; never duplicate rows to satisfy a quota."""
    ids=[r['metadata']['source_record_id'] for r in rows]
    require(len(ids)==len(set(ids)),'DUPLICATE_RECORD_ID')
    require(sum(course_quotas.values())==sum(task_quotas.values()),'QUOTA_TOTAL')
    require(all(type(v) is int and v>=0 for v in [*course_quotas.values(),*task_quotas.values()]),'QUOTA_TYPE')
    cells={};capacity={};adj={}
    def edge(a,b,n):
        capacity[a,b]=n;capacity[b,a]=0;adj.setdefault(a,[]).append(b);adj.setdefault(b,[]).append(a)
    rank=lambda r:hashlib.sha256(f'{seed}:{r["metadata"]["source_record_id"]}'.encode()).hexdigest()
    for row in rows:
        m=row['metadata'];cells.setdefault((m['course_code'],m['task_type']),[]).append(row)
    for c,n in sorted(course_quotas.items()):edge('start','c:'+c,n)
    for c in sorted(course_quotas):
        for task in sorted(task_quotas):edge('c:'+c,'t:'+task,len(cells.get((c,task),[])))
    for task,n in sorted(task_quotas.items()):edge('t:'+task,'end',n)
    flow=0
    while True:
        parent={'start':None};queue=deque(['start'])
        while queue and 'end' not in parent:
            a=queue.popleft()
            for b in adj[a]:
                if b not in parent and capacity[a,b]>0:parent[b]=a;queue.append(b)
        if 'end' not in parent:break
        node='end';amount=sum(course_quotas.values())
        while parent[node] is not None:amount=min(amount,capacity[parent[node],node]);node=parent[node]
        node='end'
        while parent[node] is not None:
            a=parent[node];capacity[a,node]-=amount;capacity[node,a]+=amount;node=a
        flow+=amount
    require(flow==sum(course_quotas.values()),'QUOTAS_INFEASIBLE')
    selected=[]
    for c in sorted(course_quotas):
        for task in sorted(task_quotas):
            count=capacity['t:'+task,'c:'+c]
            selected.extend(sorted(cells.get((c,task),[]),key=rank)[:count])
    return sorted(selected,key=rank)


def tokenize_row(payload,tokenizer,limits):
    prompt=tokenizer.apply_chat_template(payload['prompt'],tokenize=True,add_generation_prompt=True)
    full=tokenizer.apply_chat_template(payload['prompt']+payload['completion'],tokenize=True,add_generation_prompt=False)
    require(isinstance(prompt,list) and isinstance(full,list) and all(type(n) is int for n in full+prompt),'TOKENIZER_IDS')
    require(full[:len(prompt)]==prompt,'CHAT_TEMPLATE_PREFIX')
    completion=full[len(prompt):];eos=tokenizer.eos_token_id
    require(completion.count(eos)==1,'COMPLETION_EOS')
    eos_position=len(prompt)+completion.index(eos)
    tail=full[eos_position+1:]
    require(not tail or tail==tokenizer.encode('\n',add_special_tokens=False),'COMPLETION_POST_EOS')
    require(eos_position>len(prompt),'EMPTY_SUPERVISED_COMPLETION')
    require(len(prompt)<=limits['max_prompt_tokens'] and len(completion)<=limits['max_completion_tokens'] and len(full)<=limits['max_sequence_tokens'],'TOKEN_BUDGET')
    labels=[-100]*len(prompt)+full[len(prompt):eos_position+1]+[-100]*len(tail)
    return dict(input_ids=full,attention_mask=[1]*len(full),labels=labels,prompt_tokens=len(prompt),
                completion_tokens=len(completion),sequence_tokens=len(full),eos_position=eos_position,
                supervised_tokens=eos_position+1-len(prompt))


def prepare(contract,source_archive,tokenizer_folder,output,repo=ROOT):
    import html
    from importlib.metadata import version
    from apps.ai.providers.base import GenerationError
    from scripts.w6.contracts import (read_json,load_archive,SourceVerifier,assert_source_snapshot,
        sha_file,sha_bytes,write_json,write_jsonl,write_once)
    from scripts.w6.tokenizer import load_tokenizer
    from scripts.w6.intake import intake_report
    assert_source_snapshot(contract)
    registry=Path(repo)/contract['source_manifest']['path']
    require(sha_file(registry)==contract['source_manifest']['sha256'],'SOURCE_REGISTRY_HASH')
    data=load_archive(source_archive,contract['expected_compact'])
    require(data['config']['tokenizer']['revision']==contract['model']['tokenizer_revision'],'TOKENIZER_REVISION')
    tokenizer=load_tokenizer(tokenizer_folder,contract,data['config']['tokenizer'])
    verifier=SourceVerifier(read_json(registry),repo);verifier.check_registry()
    pool=[];excluded=[];source_lookup={r['metadata']['record_id']:r for r in data['records']}
    for row in data['records']:
        if row['metadata']['split']==contract['selection']['forbidden_split']:continue
        try:
            verifier.check(row)
            converted=convert_row(row['payload'],row['metadata'])
            converted['tokenized']=tokenize_row(converted['payload'],tokenizer,contract['token_limits'])
            pool.append(converted)
        except (ValueError,GenerationError) as exc:
            excluded.append({'source_record_id':row['metadata']['record_id'],
                             'reason':getattr(exc,'validation_reason',str(exc))})
    selected={}
    for split in ('train','validation'):
        spec=contract['selection'][split]
        selected[split]=select_records([r for r in pool if r['metadata']['split']==split],
            spec['courses'],spec['tasks'],contract['selection']['seed'])
    ids={s:[r['metadata']['source_record_id'] for r in rr] for s,rr in selected.items()}
    require(not set(ids['train'])&set(ids['validation']),'PILOT_SPLIT_LEAKAGE')
    forbidden=sorted(r['metadata']['record_id'] for r in data['records'] if r['metadata']['split']=='instruction_holdout')
    require(not set(forbidden)&set(ids['train']+ids['validation']),'HOLDOUT_IN_PILOT')
    output=Path(output);files={}
    def save_json(name,obj):write_json(output/name,obj);files[name]=dict(sha256=sha_file(output/name),size_bytes=(output/name).stat().st_size)
    def save_rows(name,rows):write_jsonl(output/name,rows);files[name]=dict(sha256=sha_file(output/name),size_bytes=(output/name).stat().st_size)
    def save_bytes(name,raw):write_once(output/name,raw);files[name]=dict(sha256=sha_file(output/name),size_bytes=(output/name).stat().st_size)
    stats={};counts=[];mapping_rows=[];review=[]
    for split,rows in selected.items():
        metadata=[];tokenized=[]
        for index,row in enumerate(rows):
            rid=row['metadata']['source_record_id']
            metadata.append({**row['metadata'],'row_index':index})
            tokenized.append({'record_id':rid,**row['tokenized']})
            counts.append({'record_id':rid,'split':split,**{k:v for k,v in row['tokenized'].items() if k not in ('input_ids','labels','attention_mask')}})
            mapping_rows.append({'record_id':rid,'split':split,'assignments':row['mapping'],
                                 'semantic_peer_review':'NOT_ASSERTED'})
            old=source_lookup[rid]['payload'];user=loads(old['prompt'][-1]['content'])
            review.append('<details><summary>'+html.escape(rid+' / '+split+' / '+row['metadata']['task_type'])+'</summary>'+
                '<h3>Câu hỏi</h3><p>'+html.escape(user['question'])+'</p><h3>Đáp án W5</h3><pre>'+html.escape(old['completion'][0]['content'])+
                '</pre><h3>Completion W6</h3><pre>'+html.escape(row['payload']['completion'][0]['content'])+'</pre><h3>Nguồn</h3>'+
                ''.join('<p>'+html.escape(f"[{c['citation_label']}] {c['document_title']} / trang {c['page_number']}")+'</p><pre>'+html.escape(c['text'])+'</pre>' for c in user['evidence'])+'</details>')
        save_rows(split+'.jsonl',[r['payload'] for r in rows])
        save_rows(split+'.metadata.jsonl',metadata)
        save_rows('tokenized-'+split+'.jsonl',tokenized)
        stats[split]={'count':len(rows),'tasks':dict(Counter(r['metadata']['task_type'] for r in rows)),
                      'courses':dict(Counter(r['metadata']['course_code'] for r in rows)),
                      'authors':dict(Counter(r['metadata']['author_member'] for r in rows))}
    save_json('training-contract.json',contract)
    save_json('selection.json',dict(seed=42,source_archive_sha256=data['archive_sha256'],splits=ids,
        excluded_holdout_ids=forbidden,selection_policy=contract['selection'],stats=stats))
    save_rows('source-rows.jsonl',[source_lookup[rid] for split in ('train','validation') for rid in ids[split]])
    save_rows('mapping-audit.jsonl',mapping_rows)
    save_json('intake-report.json',intake_report(data))
    save_json('tokenizer-reference.json',data['config']['tokenizer'])
    save_json('source-verification.json',dict(status='SELECTED_SOURCES_CHECKED_AGAINST_LOCAL_PDFS',
        registry_sha256=sha_file(registry),registry_pdfs_checksum_verified=len(verifier.sources),
        unique_pages_read=len(verifier.checked),candidate_rows_checked=442,selected_rows=160,
        matching_policy='NFC_REMOVE_WHITESPACE_ONLY',semantic_peer_approval_created=False))
    save_json('tokenization-report.json',dict(status='PASSED',records=counts,record_count=len(counts),
        limits=contract['token_limits'],silent_truncation=False,model_weights_loaded=False,gpu_used=False,
        packages={p:version(p) for p in ('transformers','tokenizers','huggingface-hub','pypdf','jinja2')},
        code_hashes={p:sha_file(ROOT/p) for p in ['scripts/w6/contracts.py','scripts/w6/prepare_pilot.py','scripts/w6/tokenizer.py']},
        exclusions=excluded,eligible_pool=len(pool),source_nonholdout_rows=442))
    eval_rows=select_records(selected['validation'],{'THMLN':8,'KTCTMLN':6,'CNXHKH':6},
                            {'qa':12,'summary':4,'hint':2,'insufficient_evidence':2},42)
    save_json('evaluation-selection.json',dict(scope='DEVELOPMENT_VALIDATION_NOT_HELDOUT_TEST',
        record_ids=[r['metadata']['source_record_id'] for r in eval_rows],count=20,selected_before_adapter_outputs=True))
    review_html='<!doctype html><html lang="vi"><meta charset="utf-8"><title>W6 pilot mapping audit</title><style>body{font:16px system-ui;max-width:1050px;margin:30px auto;padding:20px}details{border-bottom:1px solid #ccc;padding:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f5;padding:12px}summary{cursor:pointer;font-weight:bold}</style><h1>W6 pilot — đối chiếu ánh xạ</h1><p>160 mẫu đã kiểm kỹ thuật. Đây không phải chữ ký review hoặc bằng chứng cải thiện model. Mã nguồn được giữ từ citation W5, không suy ra bằng độ tương tự.</p>'+''.join(review)+'</html>'
    save_bytes('mapping-audit.html',review_html.encode('utf-8'))
    manifest=dict(schema_version='w6-pilot-manifest-v1',status='TECHNICAL_DATA_READY_FOR_RECIPIENT_CHECK',
        files=files,contract_sha256=digest(contract),source_archive_sha256=data['archive_sha256'],
        source_package_manifest_sha256=data['manifest']['source_package_manifest_sha256'],
        counts={s:len(rows) for s,rows in selected.items()},training='NOT_RUN',human_peer_approval_recorded=False,
        excluded_rows=excluded,public_redistribution_allowed=False,holdout_payload_included=False)
    write_json(output/'manifest.json',manifest)
    sums={**files,'manifest.json':dict(sha256=sha_file(output/'manifest.json'))}
    write_once(output/'SHA256SUMS.txt',''.join(f'{v["sha256"]}  {k}\n' for k,v in sorted(sums.items())).encode())
    return manifest


def main():
    import argparse
    from scripts.w6.contracts import read_json,sha_file
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--contract',type=Path,required=True);p.add_argument('--source-package',type=Path,required=True)
    p.add_argument('--tokenizer',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();manifest=prepare(read_json(args.contract),args.source_package,args.tokenizer,args.output)
    print('PILOT_PREPARED:',manifest['counts'],'manifest_sha256='+sha_file(args.output/'manifest.json'))


if __name__=='__main__':main()
