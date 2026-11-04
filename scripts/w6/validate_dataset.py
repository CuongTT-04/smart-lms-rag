"""Recompute W6 payload provenance, physical splits, tokenizer IDs and loss masks."""
import argparse
import sys
from collections import Counter
from pathlib import Path
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.w6.contracts import (ROOT,read_json,jsonl,within,require,sha_file,digest,
                                 write_json,SourceVerifier,assert_source_snapshot)
from scripts.w6.prepare_pilot import convert_row,tokenize_row

REQUIRED_FILES={'training-contract.json','selection.json','source-rows.jsonl',
                *(s+suffix for s in ('train','validation') for suffix in ('.jsonl','.metadata.jsonl')),
                'tokenized-train.jsonl','tokenized-validation.jsonl'}


def validate(manifest_path,tokenizer,*,expected_manifest_sha256=None,contract_path=None,source_root=None):
    manifest_path=Path(manifest_path).resolve();folder=manifest_path.parent
    manifest_sha=sha_file(manifest_path)
    if expected_manifest_sha256:require(manifest_sha==expected_manifest_sha256,'MANIFEST_HASH')
    manifest=read_json(manifest_path)
    require(REQUIRED_FILES<=set(manifest['files']),'MISSING_PAYLOAD_MEMBERS')
    require(not any('holdout' in n.lower() or n.endswith('.zip') for n in manifest['files']),'HOLDOUT_PAYLOAD_FORBIDDEN')
    for name,info in manifest['files'].items():
        path=within(folder,name)
        require(path.is_file() and path.stat().st_size==info['size_bytes'] and sha_file(path)==info['sha256'],'PAYLOAD_FILE_INTEGRITY:'+name)
    sums={}
    for line in (folder/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        sha,name=line.split('  ',1);require(name not in sums,'DUPLICATE_SUM');sums[name]=sha
    require(set(sums)==set(manifest['files'])|{manifest_path.name},'CHECKSUM_FILE_SET')
    require(all(sha_file(within(folder,name))==value for name,value in sums.items()),'CHECKSUM_FILE_INTEGRITY')
    contract=read_json(folder/'training-contract.json')
    require(digest(contract)==manifest['contract_sha256'],'CONTRACT_HASH')
    if contract_path:require(digest(read_json(contract_path))==digest(contract),'EXTERNAL_CONTRACT_MISMATCH')
    if 'source_code_sha256' in contract:assert_source_snapshot(contract)
    selection=read_json(folder/'selection.json')
    require(set(selection['splits'])=={'train','validation'},'PILOT_SPLITS')
    all_ids=selection['splits']['train']+selection['splits']['validation']
    require(len(all_ids)==len(set(all_ids)),'DUPLICATE_PILOT_ID')
    require(not set(all_ids)&set(selection['excluded_holdout_ids']),'HOLDOUT_RECORD_FORBIDDEN')
    originals=jsonl((folder/'source-rows.jsonl').read_bytes())
    lookup={r['metadata']['record_id']:r for r in originals}
    require(len(originals)==len(lookup) and set(lookup)==set(all_ids),'SOURCE_ROWS_BINDING')
    registry=None
    if source_root:
        source_file=within(source_root,contract['source_manifest']['path'])
        require(sha_file(source_file)==contract['source_manifest']['sha256'],'SOURCE_REGISTRY_HASH')
        registry=SourceVerifier(read_json(source_file),source_root);registry.check_registry()
    stats={};used_groups={};used_families={};maximum=0;supervised=0
    for split in ('train','validation'):
        payloads=jsonl((folder/(split+'.jsonl')).read_bytes())
        metadata=jsonl((folder/(split+'.metadata.jsonl')).read_bytes())
        tokenized=jsonl((folder/('tokenized-'+split+'.jsonl')).read_bytes())
        expected=contract['selection'][split]
        require(len(payloads)==len(metadata)==len(tokenized)==expected['count']==manifest['counts'][split]==len(selection['splits'][split]),'PHYSICAL_SPLIT_COUNT')
        for index,(payload,m,tokens) in enumerate(zip(payloads,metadata,tokenized)):
            rid=selection['splits'][split][index]
            require(m['source_record_id']==rid and m['split']==split and type(m['row_index']) is int and m['row_index']==index,'PHYSICAL_SPLIT_BINDING')
            original=lookup[rid];old_m=original['metadata']
            require(old_m['split']==split and old_m['record_id']==rid and digest(original['payload'])==old_m['sft_sha256'],'ORIGINAL_SPLIT_PROVENANCE')
            regenerated=convert_row(original['payload'],old_m)
            require(digest(payload)==m['training_payload_sha256']==digest(regenerated['payload']),'PAYLOAD_PROVENANCE')
            require(m=={**regenerated['metadata'],'row_index':index},'METADATA_PROVENANCE')
            for key in ('input_ids','attention_mask','labels'):
                require(isinstance(tokens.get(key),list) and all(type(n) is int for n in tokens[key]),'TOKEN_ARRAY_TYPE')
            expected_tokens={'record_id':rid,**tokenize_row(payload,tokenizer,contract['token_limits'])}
            require(tokens==expected_tokens,'TOKENIZED_RECOMPUTATION')
            maximum=max(maximum,tokens['sequence_tokens']);supervised+=tokens['supervised_tokens']
            for group in old_m['source_group_ids']:
                require(group not in used_groups or used_groups[group]==split,'SOURCE_SPLIT_LEAKAGE');used_groups[group]=split
            family=old_m['variant_family_id']
            require(family not in used_families or used_families[family]==split,'FAMILY_SPLIT_LEAKAGE');used_families[family]=split
            if registry:registry.check(original)
        courses=dict(Counter(m['course_code'] for m in metadata));tasks=dict(Counter(m['task_type'] for m in metadata))
        require(courses==expected['courses'] and tasks==expected['tasks'],'SELECTION_QUOTAS')
        stats[split]={'count':len(payloads),'courses':courses,'tasks':tasks}
    eval_file=folder/'evaluation-selection.json'
    if eval_file.exists():
        chosen=read_json(eval_file)['record_ids']
        require(len(chosen)==20 and len(set(chosen))==20 and set(chosen)<=set(selection['splits']['validation']),'EVAL_NOT_FROM_VALIDATION')
    return dict(schema_version='w6-pilot-verification-v1',passed=True,records_checked=len(all_ids),
        manifest_sha256=manifest_sha,contract_sha256=digest(contract),stats=stats,
        physical_split_and_sidecar_binding='PASSED',original_payload_provenance='RECOMPUTED_FROM_SELECTED_SOURCE_ROWS',
        original_candidate_content_hash_scope='RETAINED_FROM_AUTHENTICATED_COMPACT_METADATA_NOT_RECOMPUTED',
        tokenizer_ids_labels_and_eos='RECOMPUTED',tokenizer_class=type(tokenizer).__name__,
        max_sequence_tokens=maximum,supervised_tokens=supervised,
        holdout_records_included=0,pdf_source_recheck='PASSED' if registry else 'NOT_REQUESTED_USE_PREPARATION_SOURCE_REPORT',
        source_pages_rechecked=len(registry.checked) if registry else 0,
        receipt_authentication='EXTERNAL_MANIFEST_HASH_PROVIDED' if expected_manifest_sha256 else 'INTEGRITY_ONLY_NO_EXTERNAL_RECEIPT',
        human_peer_approval_created=False,gpu_used=False,model_weights_loaded=False,training='NOT_RUN')


def main():
    from scripts.w6.tokenizer import load_tokenizer
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--tokenizer',type=Path,required=True)
    p.add_argument('--contract',type=Path);p.add_argument('--expected-manifest-sha256')
    p.add_argument('--source-root',type=Path);p.add_argument('--report',type=Path,required=True)
    args=p.parse_args();folder=args.manifest.parent
    contract=read_json(folder/'training-contract.json')
    tokenizer=load_tokenizer(args.tokenizer,contract,read_json(folder/'tokenizer-reference.json'))
    report=validate(args.manifest,tokenizer,expected_manifest_sha256=args.expected_manifest_sha256,
                    contract_path=args.contract,source_root=args.source_root)
    write_json(args.report,report)
    print('PILOT_VERIFICATION_PASSED:',report['records_checked'],'rows; exact tokenizer/EOS/masks/split/provenance checked; training NOT_RUN.')


if __name__=='__main__':main()
