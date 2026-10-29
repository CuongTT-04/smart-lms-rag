"""Prepare a grouped, CPU-audited internal-research SFT package without model weights."""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import os
from pathlib import Path
import random
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from filelock import FileLock
from scripts.instruction.common import (canonical, check_internal_research, digest, guard_output,
    json_bytes, jsonl_bytes, load_resources, read_json, read_jsonl, read_reviews, require,
    validate_records, validate_reviews)
from scripts.instruction.export_sft_dataset import connected_components, export, SPLITS, validate_plan


def make_plan(records, contract):
    components = connected_components(records)
    require(3 <= len(components) <= 18, 'GROUP_PLANNER_REQUIRES_3_TO_18_COMPONENTS')
    ratios = [contract['split']['ratio_targets'][name] for name in SPLITS]
    require(all(0 < ratio < 1 for ratio in ratios) and abs(sum(ratios)-1) < 1e-9, 'INVALID_SPLIT_RATIOS')
    random.Random(contract['split']['seed']).shuffle(components)
    by_id = {row['record_id']: row for row in records}
    courses = sorted({row['course_code'] for row in records})
    tasks = sorted({row['task_type'] for row in records})

    def features(ids):
        rows = [by_id[key] for key in ids]
        return [len(rows), *[sum(row['course_code'] == name for row in rows) for name in courses],
                *[sum(row['task_type'] == name for row in rows) for name in tasks]]

    vectors = [features(ids) for ids in components]
    totals = features(by_id)
    weights = [4, *([1]*len(courses)), *([0.25]*len(tasks))]
    limit = 1 << len(components)
    sums = [[0]*len(totals) for _ in range(limit)]
    costs = [[0.0]*limit for _ in SPLITS]
    # Precomputed subset costs make exhaustive, whole-component assignment practical for A's 14 sources.
    for mask in range(1, limit):
        bit = mask & -mask
        sums[mask] = [a+b for a,b in zip(sums[mask ^ bit], vectors[bit.bit_length()-1])]
        for index, ratio in enumerate(ratios):
            costs[index][mask] = sum(weight*(actual-ratio*total)**2
                                     for weight,actual,total in zip(weights,sums[mask],totals))
    all_bits = limit-1
    best = None
    for validation in range(1, all_bits):
        remaining = all_bits ^ validation
        holdout = (remaining-1) & remaining
        while holdout:
            train = remaining ^ holdout
            score = costs[0][train]+costs[1][validation]+costs[2][holdout]
            if best is None or score < best[0]:
                best = (score,train,validation,holdout)
            holdout = (holdout-1) & remaining
    require(best is not None, 'NO_NONEMPTY_GROUP_SPLIT')
    assignments = {}
    for split, mask in zip(SPLITS, best[1:]):
        for index, ids in enumerate(components):
            if mask & (1 << index):
                assignments.update({key:split for key in ids})
    plan = {'seed':contract['split']['seed'], 'assignments':assignments,
            'record_hashes':{key:by_id[key]['content_sha256'] for key in sorted(by_id)}}
    counts, count = validate_plan(records,plan,contract)
    report = {'method':'exhaustive_whole_components_seeded_tie_order',
        'objective':'4*sample_count_SSE + course_count_SSE + 0.25*task_count_SSE against ratio targets',
        'objective_value':best[0], 'component_count':count, 'split_counts':counts,
        'ratio_targets':contract['split']['ratio_targets'],
        'actual_ratios':{name:counts[name]/len(records) for name in SPLITS},
        'components':components,
        'course_counts':{name:dict(Counter(by_id[key]['course_code'] for key in assignments if assignments[key]==name)) for name in SPLITS},
        'task_counts':{name:dict(Counter(by_id[key]['task_type'] for key in assignments if assignments[key]==name)) for name in SPLITS},
        'limitation':'Whole-source groups constrain ratios and course coverage. This member-A-only plan must be reconsidered on the combined A/B data before a group release.'}
    return plan, report


def tokenizer_provenance(folder, contract):
    folder = Path(folder).resolve()
    required = {'tokenizer.json','tokenizer_config.json','vocab.json','merges.txt','config.json'}
    allowed = required | {'special_tokens_map.json','chat_template.jinja','added_tokens.json'}
    names = {path.name for path in folder.iterdir() if path.is_file()}
    require(required <= names <= allowed, 'UNEXPECTED_TOKENIZER_FILES')
    files = {}
    for name in sorted(names):
        path = folder/name
        require(path.resolve().is_relative_to(folder), 'UNSAFE_TOKENIZER_PATH')
        metadata = folder/'.cache/huggingface/download'/(name+'.metadata')
        require(metadata.is_file(), 'TOKENIZER_DOWNLOAD_METADATA_MISSING')
        lines = metadata.read_text(encoding='utf-8').splitlines()
        require(len(lines)>=2 and lines[0]==contract['format']['tokenizer_revision'], 'TOKENIZER_REVISION_MISMATCH')
        data = path.read_bytes()
        etag = lines[1].strip('"')
        actual = digest(data) if len(etag)==64 else hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        require(actual==etag, 'TOKENIZER_BLOB_CHECKSUM_MISMATCH')
        files[name] = {'sha256':digest(data),'size_bytes':len(data),'hub_etag':etag}
    return {'model_id':contract['format']['model_id'], 'revision':contract['format']['tokenizer_revision'],
            'verification':'pinned_hub_download_metadata_and_blob_checksums','files':files}


def load_tokenizer(folder, contract):
    require(importlib.metadata.version('transformers')==contract['format']['transformers_reference'],
            'TRANSFORMERS_VERSION_MISMATCH')
    provenance = tokenizer_provenance(folder,contract)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(folder),local_files_only=True,trust_remote_code=False,use_fast=True)
    require(tokenizer.is_fast and tokenizer.chat_template and tokenizer.eos_token_id is not None and
            tokenizer.pad_token_id is not None, 'INVALID_CHAT_TOKENIZER')
    provenance.update(tokenizer_class=type(tokenizer).__name__,
        chat_template_sha256=digest(tokenizer.chat_template.encode('utf-8')),
        eos_token_id=tokenizer.eos_token_id,pad_token_id=tokenizer.pad_token_id,
        packages={name:importlib.metadata.version(name) for name in ('transformers','tokenizers','huggingface-hub')})
    return tokenizer, provenance


def tokenize_example(sample, tokenizer, limits):
    require(set(sample)=={'prompt','completion'}, 'INVALID_SFT_FIELDS')
    prompt,completion = sample['prompt'],sample['completion']
    require([m.get('role') for m in prompt]==['system','user'] and
            len(completion)==1 and completion[0].get('role')=='assistant' and
            isinstance(completion[0].get('content'),str) and bool(completion[0]['content'].strip()), 'INVALID_SFT_ROLES')
    require(all(not any(token in message['content'] for token in tokenizer.all_special_tokens)
                for message in prompt+completion), 'RESERVED_TOKEN_IN_DATA')
    prompt_text = tokenizer.apply_chat_template(prompt,tokenize=False,add_generation_prompt=True)
    full_text = tokenizer.apply_chat_template(prompt+completion,tokenize=False,add_generation_prompt=False)
    require(full_text.startswith(prompt_text), 'CHAT_TEMPLATE_PREFIX_MISMATCH')
    ids = list(tokenizer(full_text,add_special_tokens=False)['input_ids'])
    prompt_ids = list(tokenizer(prompt_text,add_special_tokens=False)['input_ids'])
    require(ids==list(tokenizer.apply_chat_template(prompt+completion,tokenize=True,add_generation_prompt=False)),
            'CHAT_TEMPLATE_TOKENIZATION_MISMATCH')
    start = len(prompt_ids)
    require(ids[:start]==prompt_ids, 'TOKEN_BOUNDARY_MISMATCH')
    tail = ids[start:]
    require(tail.count(tokenizer.eos_token_id)==1, 'COMPLETION_EOS_COUNT')
    eos = start+tail.index(tokenizer.eos_token_id)
    require(eos>start, 'EMPTY_SUPERVISED_TARGET')
    require(tokenizer.decode(ids[start:eos],skip_special_tokens=False,clean_up_tokenization_spaces=False)==completion[0]['content'],
            'COMPLETION_ROUNDTRIP_MISMATCH')
    require(not tokenizer.decode(ids[eos+1:],skip_special_tokens=False,clean_up_tokenization_spaces=False).strip(),
            'NON_FORMAT_TEXT_AFTER_EOS')
    require(start<=limits['max_prompt_tokens'], 'PROMPT_TOKEN_LIMIT')
    require(len(ids)-start<=limits['max_completion_tokens'], 'COMPLETION_TOKEN_LIMIT')
    require(len(ids)<=limits['max_sequence_tokens'], 'SEQUENCE_TOKEN_LIMIT')
    labels = [-100]*len(ids)
    labels[start:eos+1] = ids[start:eos+1]
    encoded = {'input_ids':ids,'attention_mask':[1]*len(ids),'labels':labels}
    stats = {'prompt_tokens':start,'completion_tokens_with_formatting':len(ids)-start,
             'sequence_tokens':len(ids),'supervised_target_tokens':eos-start,
             'supervised_tokens_including_eos':eos-start+1,'trailing_masked_format_tokens':len(ids)-eos-1,
             'encoded_sha256':digest(canonical(encoded))}
    return encoded, stats


def collate(examples, *, pad_token_id, max_sequence_tokens=4096, pad_to_multiple_of=8):
    """Right-pad audited examples; CausalLM, not this collator, shifts labels."""
    require(bool(examples) and type(pad_to_multiple_of) is int and pad_to_multiple_of>0, 'INVALID_BATCH')
    size = max(len(row['input_ids']) for row in examples)
    size = ((size+pad_to_multiple_of-1)//pad_to_multiple_of)*pad_to_multiple_of
    require(size<=max_sequence_tokens, 'PADDED_SEQUENCE_TOKEN_LIMIT')
    result = {name:[] for name in ('input_ids','attention_mask','labels')}
    for row in examples:
        ids,labels,attention = row['input_ids'],row['labels'],row['attention_mask']
        require(len(ids)==len(labels)==len(attention) and bool(ids) and attention==[1]*len(ids) and
                all(type(x) is int for x in ids) and all(type(x) is int and (x==-100 or x==token) for x,token in zip(labels,ids)) and
                any(x!=-100 for x in labels), 'INVALID_AUDITED_ENCODING')
        missing = size-len(ids)
        result['input_ids'].append(ids+[pad_token_id]*missing)
        result['attention_mask'].append(attention+[0]*missing)
        result['labels'].append(labels+[-100]*missing)
    return result


def prepare(records,reviews,output,resources,tokenizer,provenance, *, input_paths=()):
    output = guard_output(output,input_paths)
    check_internal_research(resources)
    require(output.is_relative_to((resources.root/'.private/instruction').resolve()), 'RESEARCH_OUTPUT_MUST_STAY_PRIVATE')
    require(records and all(row['author_member']=='A' for row in records), 'MEMBER_A_ONLY')
    validate_records(records,resources,private_draft=True)
    validate_reviews(records,reviews,resources)
    plan, split_report = make_plan(records,resources.contract)
    require(not output.exists(), 'OUTPUT_ALREADY_EXISTS')
    output.parent.mkdir(parents=True,exist_ok=True)
    with FileLock(str(output)+'.lock',timeout=10):
        require(not output.exists(), 'OUTPUT_ALREADY_EXISTS')
        temporary = Path(tempfile.mkdtemp(prefix='.prepare-',dir=output.parent))
        try:
            package = temporary/'package'
            manifest = export(records,reviews,plan,package,resources,internal_research=True)
            metadata = read_jsonl(package/'metadata.jsonl')
            by_position = {(row['split'],row['row_index']):row for row in metadata}
            stats = []
            (package/'tokenized').mkdir()
            for split in SPLITS:
                examples = []
                for index,sample in enumerate(read_jsonl(package/(split+'.jsonl'))):
                    encoded,summary = tokenize_example(sample,tokenizer,resources.contract['format'])
                    meta = by_position[(split,index)]
                    summary.update(record_id=meta['record_id'],content_sha256=meta['content_sha256'],split=split,row_index=index)
                    stats.append(summary)
                    examples.append({'record_id':meta['record_id'],**encoded})
                for start in range(0,len(examples),8):
                    group = examples[start:start+8]
                    batch = collate(group,pad_token_id=tokenizer.pad_token_id,
                                    max_sequence_tokens=resources.contract['format']['max_sequence_tokens'])
                    for row,attention,labels in zip(group,batch['attention_mask'],batch['labels']):
                        require(labels[:len(row['labels'])]==row['labels'] and
                                all(value==-100 for value in labels[len(row['labels']):]) and
                                sum(attention)==len(row['input_ids']), 'BATCH_MASK_MISMATCH')
                (package/'tokenized'/(split+'.jsonl')).write_bytes(jsonl_bytes(examples))
            audit = {'status':'PASSED','scope':'MEMBER_A_INTERNAL_RESEARCH_DATA_ONLY',
                'record_count':len(stats),'tokenizer':provenance,'split':split_report,
                'limits':{key:resources.contract['format'][key] for key in
                          ('max_prompt_tokens','max_completion_tokens','max_sequence_tokens')},
                'max_observed':{key:max(row[key] for row in stats) for key in
                                ('prompt_tokens','completion_tokens_with_formatting','sequence_tokens')},
                'checks':['template_prefix','token_prefix','target_roundtrip','single_supervised_eos',
                          'nonempty_target','no_silent_truncation','prompt_and_padding_masked','batch_padding',
                          'group_disjointness','current_hash_reviews','metadata_row_join'],
                'loss_scope':'completion_content_and_eos_only','padding_side':'right','label_shift':'handled_by_causal_lm_not_pre_shifted',
                'assistant_only_loss_assumed':False,'rows':sorted(stats,key=lambda row:row['record_id']),
                'training':'NOT_RUN','model_loaded':False,'gpu_used':False,'final_b_review':'PENDING',
                'group_release_ready':False,'trainer_and_qlora_configuration_audited':False}
            audit['tool_sha256']={name:digest((ROOT/name).read_bytes()) for name in
                ('scripts/instruction/common.py','scripts/instruction/export_sft_dataset.py','scripts/instruction/prepare_sft.py')}
            (package/'tokenization-audit.json').write_bytes(json_bytes(audit))
            (package/'split-plan.json').write_bytes(json_bytes(plan))
            (package/'input-contract.snapshot.json').write_bytes(json_bytes(resources.contract))
            manifest.update(status='MEMBER_A_INTERNAL_RESEARCH_TECHNICALLY_AUDITED',training_ready=True,
                training_readiness_scope='DATA_ONLY_FOR_PRIVATE_INTERNAL_EXPERIMENT_NOT_GROUP_RELEASE',
                member_scope='A_ONLY_250_TARGET',b_data_review='PENDING_INPUT',group_release_ready=False,
                tokenizer=provenance,max_observed_tokens=audit['max_observed'])
            manifest['validation']['tokenizer_eos_loss_mask']='PASSED'
            manifest['validation']['group_split']='PASSED'
            manifest['limitation']='Technical dataset audit only, not verified source rights, model quality, trainer/QLoRA configuration, completed training or final B approval. Combined A/B data require a new group split and audit.'
            manifest['files']={str(path.relative_to(package)).replace('\\','/'):
                {'sha256':digest(path.read_bytes()),'size_bytes':path.stat().st_size}
                for path in sorted(package.rglob('*')) if path.is_file() and path.name!='manifest.json'}
            (package/'manifest.json').write_bytes(json_bytes(manifest))
            require(not output.exists(), 'OUTPUT_ALREADY_EXISTS')
            os.rename(package,output)
        finally:
            shutil.rmtree(temporary,ignore_errors=True)
    return manifest


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records',type=Path,required=True)
    parser.add_argument('--reviews',type=Path,required=True)
    parser.add_argument('--tokenizer',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--contract',type=Path,default=ROOT/'data/instruction/input-contract.json')
    args=parser.parse_args(argv)
    try:
        inputs=[args.records,args.reviews,args.tokenizer,args.contract]
        guard_output(args.output,inputs)
        resources=load_resources(args.contract)
        tokenizer,provenance=load_tokenizer(args.tokenizer,resources.contract)
        result=prepare(read_jsonl(args.records),read_reviews(args.reviews),args.output,resources,
                       tokenizer,provenance,input_paths=inputs)
    except (ValueError,OSError,KeyError) as error:
        parser.exit(1,f'{type(error).__name__}: {error}\n')
    print(result['status'],result['split_counts'],result['max_observed_tokens'])


if __name__=='__main__':
    main()
