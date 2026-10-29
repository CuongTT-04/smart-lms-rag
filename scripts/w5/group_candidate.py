"""Prepare an audited combined draft; technical checks never grant peer approval."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unicodedata
from collections import Counter
from .common import ROOT, digest, content_hash, load_contract, projected, sha_file
from .splitting import build_split_plan


def source_excerpt_matches(page, excerpt):
    compact=lambda value: ''.join(unicodedata.normalize('NFC',value).split())
    return bool(compact(excerpt)) and compact(excerpt) in compact(page)


def candidate_status(count):
    return dict(status='GROUP_INTERNAL_RESEARCH_TECHNICALLY_AUDITED_CANDIDATE',record_count=count,
                group_release_ready=False,training_ready=False,peer_acceptance='PENDING_ACTUAL_MEMBERS',
                model_weights_loaded=False,training='NOT_RUN',public_redistribution_allowed=False)


def tokenizer_contract(contract):
    """Derive A's tokenizer interface solely from the frozen W5 training pins."""
    t=contract['training']
    if t['model_revision']!=t['tokenizer_revision']:raise ValueError('Conflicting model/tokenizer revisions')
    limits={k:t[k] for k in ('max_prompt_tokens','max_completion_tokens','max_sequence_tokens')}
    if any(type(v) is not int or v<=0 for v in limits.values()) or limits['max_prompt_tokens']+limits['max_completion_tokens']>limits['max_sequence_tokens']:
        raise ValueError('Invalid frozen token limits')
    library=t['tokenizer_library_reference'].split('==')
    if len(library)!=2 or library[0]!='transformers':raise ValueError('Tokenizer library is not pinned')
    return dict(format=dict(model_id=t['model_id'],model_revision=t['model_revision'],tokenizer_revision=t['tokenizer_revision'],
                            transformers_reference=library[1],**limits))


def balanced_plan(records):
    """Preserve connected components; allocate one small whole source per course
    to each evaluation split. Ratios are approximate, coverage is explicit.
    """
    if not records:raise ValueError('Empty candidate set')
    rows={r['record_id']:r for r in records}
    initial=build_split_plan(records,sorted(rows),[],42)
    groups={}
    for component in initial['components']:
        ids=component['record_ids']; courses={rows[i]['course_code'] for i in ids}
        if len(courses)!=1:raise ValueError('Cross-course component requires explicit reviewed split plan')
        groups.setdefault(next(iter(courses)),[]).append(ids)
    splits={k:[] for k in ['train','validation','instruction_holdout']}
    assignments=[]
    for course,components in sorted(groups.items()):
        if len(components)<3:raise ValueError('Need three independent source components per course')
        components.sort(key=lambda ids:(len(ids),digest({'seed':42,'ids':ids})))
        for index,ids in enumerate(components):
            split='validation' if index==0 else 'instruction_holdout' if index==1 else 'train'
            splits[split].extend(ids)
            assignments.append(dict(component_id=digest(ids),split=split,record_ids=ids))
    for ids in splits.values():ids.sort()
    return dict(seed=42,method='smallest_whole_components_per_course_seeded_ties',
                splits=splits,components=sorted(assignments,key=lambda c:c['component_id']),
                dataset_fingerprint=digest({i:rows[i]['content_sha256'] for i in sorted(rows)}),
                stats={k:dict(count=len(ids),courses=dict(Counter(rows[i]['course_code'] for i in ids)),
                              tasks=dict(Counter(rows[i]['task_type'] for i in ids))) for k,ids in splits.items()},
                limitation='Targets80/10/10 are approximate: whole-source grouping and all-course coverage take precedence. No exhaustive optimum claimed.',
                acceptance='DRAFT_SPLIT_NOT_FINAL_PEER_ACCEPTED')


def adapted_contract(records, contract):
    """Versioned in-memory compatibility catalog, without changing records or licenses."""
    import copy
    c=copy.deepcopy(contract)
    references={}
    for row in records:
        for context in row['contexts']:
            key=(context['document_id'],context['version_id'])
            if key in references and references[key]!=context['rights_reference']:
                raise ValueError('Conflicting source permission reference')
            references[key]=context['rights_reference']
    for source in c['sources']['sources']:
        key=(source['document_id'],source['version_id'])
        if key in references:
            actual=references[key]
            if actual not in (source['rights_evidence_reference'],'UNVERIFIED:'+source['source_group_id']):
                raise ValueError('Unrecognized internal-research reference')
            source['rights_evidence_reference']=actual
    c['quality']['evidence_whitespace_policy']='NFC_REMOVE_WHITESPACE'
    c['fingerprint']=digest({k:v for k,v in c.items() if k!='fingerprint'})
    return c


def prepare_group(records, output, tokenizer_folder, *, input_paths=()):
    from .quality import validate_records
    from scripts.instruction.prepare_sft import load_tokenizer, tokenize_example, collate
    from scripts.instruction.common import guard_output
    output=guard_output(output,input_paths)
    if not output.is_relative_to((ROOT/'.private').resolve()):raise ValueError('Group data must remain private')
    if output.exists():raise FileExistsError('Never overwrite an audited package')
    contract=load_contract(ROOT/'data/instruction/w5/contract')
    for name,expected in contract['training']['source_hashes'].items():
        if hashlib.sha256((ROOT/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Pinned runtime source changed: '+name)
    for row in records:
        if row['content_sha256']!=content_hash(row):raise ValueError('Stale content hash')
    expected=contract['quality']
    if len(records)!=expected['target_accepted_records']:raise ValueError('Combined candidate quota not met')
    for field,quota in [('author_member',expected['target_per_author']),('task_type',expected['task_quota']),('course_code',expected['course_quota'])]:
        if dict(Counter(r[field] for r in records))!=quota:raise ValueError('Quota mismatch: '+field)
    for member in expected['target_per_author']:
        if dict(Counter(r['task_type'] for r in records if r['author_member']==member))!=expected['per_author_task_quota']:
            raise ValueError('Per-author task quota mismatch')
    adapted=adapted_contract(records,contract)
    quality=validate_records(records,adapted,ROOT)
    if not quality['passed'] or quality['findings']:raise ValueError('Combined quality findings must be resolved')
    plan=balanced_plan(records)
    a_contract=tokenizer_contract(contract)
    tokenizer,provenance=load_tokenizer(tokenizer_folder,a_contract)
    if hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()!=contract['training']['chat_template_sha256']:
        raise ValueError('Chat template changed')
    metadata=[];audits=[];files={}
    rows={r['record_id']:r for r in records}
    for split,ids in plan['splits'].items():
        payloads=[];encodings=[]
        for index,rid in enumerate(ids):
            row=rows[rid]
            payload=dict(prompt=projected(row,contract)[1],completion=[dict(role='assistant',content=row['target_text'])])
            encoded,stats=tokenize_example(payload,tokenizer,a_contract['format'])
            payloads.append(payload);encodings.append(dict(record_id=rid,**encoded))
            metadata.append(dict(record_id=rid,content_sha256=row['content_sha256'],split=split,row_index=index,
                                 sft_sha256=digest(payload),record=row,peer_review_status='PENDING'))
            audits.append(dict(record_id=rid,**stats))
        for start in range(0,len(encodings),8):
            batch=collate(encodings[start:start+8],pad_token_id=tokenizer.pad_token_id)
            for row,labels in zip(encodings[start:start+8],batch['labels']):
                if labels[:len(row['labels'])]!=row['labels'] or any(v!=-100 for v in labels[len(row['labels']):]):
                    raise ValueError('Padding labels mismatch')
        files[split+'.jsonl']=payloads;files['tokenized/'+split+'.jsonl']=encodings
    status=candidate_status(len(records))
    audit=dict(status='PASSED',scope='TECHNICAL_ONLY_NOT_PEER_ACCEPTANCE',tokenizer=provenance,
               source_policy='NFC_REMOVE_WHITESPACE; no non-whitespace change allowed',records=audits,
               loss_scope='completion content and EOS; prompt, trailing format and padding masked',**{k:v for k,v in status.items() if k!='status'})
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.group-',dir=output.parent) as tmp:
        staging=Path(tmp)/'package';staging.mkdir()
        def save(name,data,jsonl=False):
            p=staging/name;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data) if jsonl else json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        for name,data in files.items():save(name,data,True)
        save('metadata.jsonl',metadata,True);save('candidates.jsonl',[rows[i] for i in sorted(rows)],True)
        save('split-plan.json',plan);save('quality-report.json',quality);save('tokenization-audit.json',audit)
        save('contract.snapshot.json',adapted)
        manifest=dict(**status,split_counts={k:len(v) for k,v in plan['splits'].items()},
                      input_sha256={str(p):sha_file(p) for p in input_paths},
                      tool_sha256={name:sha_file(ROOT/name) for name in ['scripts/w5/group_candidate.py','scripts/w5/quality.py','scripts/instruction/prepare_sft.py']},
                      files={str(p.relative_to(staging)).replace('\\','/'):{'sha256':sha_file(p),'size_bytes':p.stat().st_size} for p in staging.rglob('*') if p.is_file()})
        save('manifest.json',manifest)
        if output.exists():raise FileExistsError('Output appeared during preparation')
        os.rename(staging,output)
    return manifest


def verify_group_package(folder, tokenizer_folder, expected_manifest_sha256):
    """Reopen every stored row and recompute tokenization; keep the package immutable."""
    from .common import read_json, read_jsonl
    from .quality import validate_records
    from scripts.instruction.prepare_sft import load_tokenizer, tokenize_example, collate
    folder=Path(folder).resolve()
    if sha_file(folder/'manifest.json')!=expected_manifest_sha256:raise ValueError('Manifest checksum mismatch')
    manifest=read_json(folder/'manifest.json')
    actual={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual!=set(manifest['files'])|{'manifest.json'}:raise ValueError('Package inventory mismatch')
    for name,entry in manifest['files'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder) or path.is_symlink():raise ValueError('Unsafe manifest path')
        if sha_file(path)!=entry['sha256'] or path.stat().st_size!=entry['size_bytes']:raise ValueError('File checksum mismatch')
    if manifest.get('group_release_ready') is not False or manifest.get('training_ready') is not False or manifest.get('peer_acceptance')!='PENDING_ACTUAL_MEMBERS':
        raise ValueError('Unexpected approval in a technical candidate')
    for name,expected in manifest['tool_sha256'].items():
        if sha_file(ROOT/name)!=expected:raise ValueError('Audit tool changed: '+name)
    records=read_jsonl(folder/'candidates.jsonl');contract=read_json(folder/'contract.snapshot.json')
    quality=validate_records(records,contract,ROOT)
    if not quality['passed'] or quality['findings']:raise ValueError('Stored source/quality checks failed')
    plan=balanced_plan(records)
    if plan!=read_json(folder/'split-plan.json'):raise ValueError('Stored split differs from deterministic plan')
    cfg=tokenizer_contract(contract)
    tokenizer,provenance=load_tokenizer(tokenizer_folder,cfg)
    audit=read_json(folder/'tokenization-audit.json')
    if provenance!=audit['tokenizer']:raise ValueError('Tokenizer provenance changed')
    metadata=read_jsonl(folder/'metadata.jsonl');by_id={r['record_id']:r for r in records}
    if len(metadata)!=len(records) or len({m['record_id'] for m in metadata})!=len(records):raise ValueError('Metadata count/IDs invalid')
    meta={m['record_id']:m for m in metadata};count=0
    for split,ids in plan['splits'].items():
        payloads=read_jsonl(folder/(split+'.jsonl'));encoded=read_jsonl(folder/'tokenized'/(split+'.jsonl'))
        if len(payloads)!=len(encoded) or len(payloads)!=len(ids):raise ValueError('Split count mismatch')
        for index,(rid,payload,stored) in enumerate(zip(ids,payloads,encoded)):
            row=by_id[rid];m=meta[rid]
            if m['record']!=row or m['content_sha256']!=content_hash(row) or m['sft_sha256']!=digest(payload) or m['row_index']!=index or m['split']!=split:
                raise ValueError('Metadata ID/hash/position mismatch')
            trusted=dict(prompt=projected(row,contract)[1],completion=[dict(role='assistant',content=row['target_text'])])
            if payload!=trusted:raise ValueError('Stored payload differs from trusted projection')
            new,stats=tokenize_example(payload,tokenizer,cfg['format'])
            if stored!=dict(record_id=rid,**new):raise ValueError('Stored token IDs/labels differ')
            count+=1
        for start in range(0,len(encoded),8):
            batch=collate(encoded[start:start+8],pad_token_id=tokenizer.pad_token_id)
            for row,labels in zip(encoded[start:start+8],batch['labels']):
                if labels[:len(row['labels'])]!=row['labels'] or any(v!=-100 for v in labels[len(row['labels']):]):raise ValueError('Readback padding mismatch')
    if count!=manifest['record_count']:raise ValueError('Final readback count mismatch')
    return dict(status='PASSED',reopened_records=count,files_checked=len(manifest['files']),
                manifest_sha256=expected_manifest_sha256,split_counts=manifest['split_counts'],
                token_ids_labels_padding_recomputed=True,source_and_benchmark_checks_recomputed=True,
                group_release_ready=False,peer_acceptance='PENDING_ACTUAL_MEMBERS',training='NOT_RUN')
