"""CLI boundaries for B-owned tools; candidate checks never imply release readiness."""
import argparse
import json
import sys
from pathlib import Path
from .common import ROOT, digest, load_contract, read_csv, read_json, read_jsonl, sha_file, within, write_json
from .quality import validate_records


def arguments(description):
    p=argparse.ArgumentParser(description=description)
    p.add_argument('--input',nargs='+',type=Path,required=True)
    p.add_argument('--contract',type=Path,default=ROOT/'data/instruction/w5/contract')
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--reviews',nargs='*',type=Path,default=[])
    p.add_argument('--adjudications',type=Path)
    p.add_argument('--fixture-mode',action='store_true')
    p.add_argument('--report',type=Path,required=True)
    return p


def inputs(args, stage):
    contract=load_contract(args.contract)
    records=[r for path in args.input for r in read_jsonl(path)]
    reviews=[r for path in args.reviews for r in read_csv(path)]
    judgments=read_csv(args.adjudications) if args.adjudications else []
    report=validate_records(records,contract,args.root,fixture_mode=args.fixture_mode,reviews=reviews,stage=stage,adjudications=judgments)
    report['input_sha256']={str(p):sha_file(p) for p in args.input+args.reviews+([args.adjudications] if args.adjudications else [])}
    return contract,records,report


def output(args, report, extra_inputs=()):
    path=args.report.resolve()
    protected=[p.resolve() for p in [*args.input,*args.reviews,*extra_inputs]]
    if args.adjudications:protected.append(args.adjudications.resolve())
    c=load_contract(args.contract)
    protected.extend(within(args.root,row['path']) for row in c['exclusion']['protected_inputs'])
    protected.extend(within(args.root,row['relative_path']) for row in c['sources']['sources'])
    if path in protected or path.is_relative_to(args.contract.resolve()): raise ValueError('Report would overwrite an input/contract')
    write_json(path,report)
    print(json.dumps(dict(passed=report['passed'],report=str(args.report),record_count=report.get('record_count',len(report.get('records',[])))),ensure_ascii=False))
    return 0 if report['passed'] else 1


def validate_main():
    p=arguments('Validate W5 candidate records and source/review gates')
    p.add_argument('--stage',choices=['candidate','release'],default='candidate')
    args=p.parse_args();_,_,report=inputs(args,args.stage)
    return output(args,report)


def split_main():
    from .splitting import build_split_plan
    p=arguments('Create split plan only from freshly validated/reviewed real candidates')
    args=p.parse_args();contract,records,quality=inputs(args,'release')
    if not quality['passed']: return output(args,quality)
    plan=build_split_plan(records,quality['eligible_ids'],quality['confirmed_pairs'],contract['split']['seed'])
    plan.update(passed=True,contract_fingerprint=contract['fingerprint'],validation_input_sha256=quality['input_sha256'])
    return output(args,plan)


def bind_release_files(records, plan, payload_paths, sidecar_paths, *, load_rows=None):
    """Bind each physical split file to its exact planned ID set before token audit."""
    load_rows = load_rows or read_jsonl
    expected_splits = {'train', 'validation', 'instruction_holdout'}
    if set(plan['splits']) != expected_splits or len(payload_paths) != 3 or len(sidecar_paths) != 3:
        raise ValueError('Release audit requires exactly three named split file pairs')
    lookup = {row['record_id']: row for row in records}
    if len(lookup) != len(records):
        raise ValueError('Duplicate candidate ID')
    order, payloads, seen, split_files = [], [], set(), set()
    for payload_path, sidecar_path in zip(payload_paths, sidecar_paths):
        split = payload_path.stem
        if split not in expected_splits or split in split_files:
            raise ValueError('Duplicate or unknown physical split filename')
        if sidecar_path.name != split + '.metadata.jsonl':
            raise ValueError('Sidecar filename does not match physical split')
        split_files.add(split)
        items, metadata = load_rows(payload_path), load_rows(sidecar_path)
        if len(items) != len(metadata):
            raise ValueError('Sidecar/payload count mismatch within split')
        expected_ids = plan['splits'][split]
        actual_ids = [row['record_id'] for row in metadata]
        if len(expected_ids) != len(set(expected_ids)) or len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
            raise ValueError('Physical split IDs do not match split plan')
        for index, (sidecar, item) in enumerate(zip(metadata, items)):
            rid = sidecar['record_id']
            if rid in seen or rid not in lookup or sidecar['split'] != split:
                raise ValueError('Duplicate/unknown ID or declared split differs from physical file')
            row = lookup[rid]
            if sidecar['content_sha256'] != row['content_sha256'] or sidecar['sft_sha256'] != digest(item):
                raise ValueError('Sidecar content/payload hash mismatch')
            if 'row_index' in sidecar and sidecar['row_index'] != index:
                raise ValueError('Sidecar row position mismatch')
            seen.add(rid)
            order.append(row)
            payloads.append(item)
    if seen != set(lookup):
        raise ValueError('Release file coverage differs from candidate set')
    return order, payloads


def training_main():
    from .training import check_training_format
    from .splitting import build_split_plan
    p=arguments('Audit A exporter payload using pinned tokenizer, no model weights')
    p.add_argument('--payload',nargs='+',type=Path,required=True)
    p.add_argument('--sidecar',nargs='+',type=Path)
    p.add_argument('--split-plan',type=Path)
    p.add_argument('--draft-mode',action='store_true',help='Token audit of unreviewed candidates; never release approval')
    args=p.parse_args()
    if args.fixture_mode and args.draft_mode: raise ValueError('Choose fixture-mode or draft-mode, not both')
    contract,records,quality=inputs(args,'candidate' if args.fixture_mode or args.draft_mode else 'release')
    extra=[*args.payload,*(args.sidecar or []),*([args.split_plan] if args.split_plan else [])]
    if not quality['passed']: return output(args,quality,extra)
    records=sorted(records,key=lambda r:r['record_id'])
    if not args.fixture_mode and not args.draft_mode:
        if not args.sidecar or not args.split_plan: raise ValueError('Real release audit requires sidecars and split plan')
        plan=read_json(args.split_plan)
        expected=build_split_plan(records,quality['eligible_ids'],quality['confirmed_pairs'],contract['split']['seed'])
        if plan.get('contract_fingerprint')!=contract['fingerprint'] or plan.get('splits')!=expected['splits'] or plan.get('dataset_fingerprint')!=expected['dataset_fingerprint']: raise ValueError('Split plan does not bind current candidates/contract')
        records,payload=bind_release_files(records,plan,args.payload,args.sidecar)
    else:
        payload=[r for path in args.payload for r in read_jsonl(path)]
    from importlib.metadata import version
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
    cfg=contract['training']
    if version('transformers')!=cfg['tokenizer_library_reference'].split('==')[1]: raise ValueError('Use pinned Transformers runtime; see W5 README')
    for path,sha in cfg['source_hashes'].items():
        from .common import within
        import hashlib
        if hashlib.sha256(within(args.root,path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=sha: raise ValueError('Pinned prompt/parser source changed: '+path)
    snapshot=snapshot_download(cfg['model_id'],revision=cfg['tokenizer_revision'],allow_patterns=['tokenizer*','vocab.json','merges.txt','config.json','*.jinja','special_tokens_map.json','added_tokens.json'])
    if Path(snapshot).name!=cfg['tokenizer_revision']: raise ValueError('Tokenizer snapshot revision mismatch')
    tokenizer=AutoTokenizer.from_pretrained(snapshot,local_files_only=True,trust_remote_code=False)
    report=check_training_format(records,payload,tokenizer,contract)
    if report['chat_template_sha256']!=cfg.get('chat_template_sha256'): raise ValueError('Chat template hash is not pinned or changed')
    report.update(fixture_mode=args.fixture_mode,draft_mode=args.draft_mode,record_count=len(records),training_ready=False,
                  input_sha256={str(path):sha_file(path) for path in args.input+args.reviews+extra})
    return output(args,report,extra)


def run(function):
    try: return function()
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'passed':False,'error':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2
    except ImportError:
        print(json.dumps({'passed':False,'error':'Missing dependency; install scripts/w5/requirements-tokenizer.txt in an isolated environment'}),file=sys.stderr)
        return 2
