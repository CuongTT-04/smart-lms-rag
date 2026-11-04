"""Create the W6 technical handoff contract from the checked-in W5 receipt."""
import subprocess
from pathlib import Path
from .contracts import ROOT,read_json,sha_bytes,write_json


def create_contract(repo=ROOT):
    repo=Path(repo);w5=read_json(repo/'Evidence/W05/manifest.json')
    code=['backend/apps/__init__.py','backend/apps/ai/__init__.py']
    for group in ('providers','prompts','rag'):
        code.extend(p.relative_to(repo).as_posix() for p in sorted((repo/'backend/apps/ai'/group).glob('*.py')))
    return dict(schema_version='ohayo-w6-training-contract-v1',contract_id='w6-pilot-evidence-v1',
        created_on='2026-11-02',plan='docs/weekly/W6/phan-cong-w6.md',
        source_git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
        owners={'data_and_verification':'Trần Tuấn Cường','trainer_and_gpu':'Vũ Nam Dương'},
        source_code_sha256={name:sha_bytes((repo/name).read_bytes().replace(b'\r\n',b'\n')) for name in code},
        source_manifest={'path':'data/instruction/w5/contract/source-manifest.json',
                         'sha256':sha_bytes((repo/'data/instruction/w5/contract/source-manifest.json').read_bytes())},
        expected_compact=dict(archive_sha256=w5['compact_package']['sha256'],
            source_package_manifest_sha256=w5['dataset']['full_package_manifest_sha256'],
            record_count=500,split_counts={'train':385,'validation':57,'instruction_holdout':58}),
        authorization=dict(scope='PRIVATE_INTERNAL_TECHNICAL_PILOT_HANDOFF',
            decision_reference='User request in current conversation 2026-11-02',
            formal_w5_review_paperwork_required_for_technical_handoff=False,
            original_peer_acceptance='PENDING_ACTUAL_MEMBERS',human_peer_approval_recorded=False,
            source_rights='DECLARED_NOT_VERIFIED',public_redistribution_allowed=False,
            recipient_content_check='Inspect mapping-audit.html before the GPU smoke; no signature is fabricated.'),
        model=dict(model_id='Qwen/Qwen2.5-7B-Instruct',revision='a09a35458c702b33eeacc393d103063234e8bc28',
                   tokenizer_revision='a09a35458c702b33eeacc393d103063234e8bc28',
                   transformers_version='4.57.6',eos_token_id=151645,pad_token_id=151643,
                   chat_template_sha256='cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f'),
        format=dict(qa='evidence_citations_v2',summary='evidence_citations_v2',
                    insufficient_evidence='{"items":[]}',hint='W5_READ_OUTLINE_COMPARE_UNCHANGED',
                    metadata_in_prompt=False,conversion='EXPLICIT_LABEL_TO_UNAMBIGUOUS_UNIT_ONLY'),
        token_limits=dict(max_prompt_tokens=1536,max_completion_tokens=512,max_sequence_tokens=2048),
        labels=dict(loss_scope='COMPLETION_AND_SINGLE_EOS_ONLY',prompt_label=-100,padding_label=-100,
                    post_eos_format_label=-100,padding_side='right',pad_to_multiple_of=8,
                    pre_padded=False,causal_label_shift='MODEL_INTERNAL_DO_NOT_SHIFT_TWICE',silent_truncation=False),
        selection=dict(seed=42,rank='sha256(seed:source_record_id)',algorithm='DETERMINISTIC_INTEGER_FLOW',
            train=dict(count=128,courses={'THMLN':52,'KTCTMLN':38,'CNXHKH':38},tasks={'qa':77,'summary':25,'hint':13,'insufficient_evidence':13}),
            validation=dict(count=32,courses={'THMLN':12,'KTCTMLN':10,'CNXHKH':10},tasks={'qa':19,'summary':7,'hint':3,'insufficient_evidence':3}),
            forbidden_split='instruction_holdout',holdout_in_handoff=False),
        training=dict(status='NOT_RUN',weights_downloaded=False,trainer_owner='Vũ Nam Dương',
                      target_global_step=50,smoke_steps=2,checkpoint_steps=[25,50],
                      preserve_base_model=True,serving_ayo_changed=False),
        handoff=dict(status='DATA_PREPARATION_NOT_YET_RUN',milestone='Tuan6',issue='W6-02',
                     new_instruction_records_authored=0,new_record_allocation_only=True))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'data/w6/training-contract.json')
    args=p.parse_args();write_json(args.output,create_contract());print('W6 contract written; no training executed.')
