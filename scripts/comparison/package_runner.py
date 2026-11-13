"""Build an allowlisted, gold-free dev runner; main cannot be exported by this tool."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
from zipfile import ZipFile

from scripts.comparison.protocol import read_rows, verify_bundle, write_bundle, write_json
from scripts.comparison.runner import LIMITS, MODEL, REVISION, audit_assets, validate_config, validate_inputs
from scripts.comparison.packing import schedule
from scripts.qlora.data import read_json, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory

ROOT=Path(__file__).resolve().parents[2]
PILOT_SHA='b56082699bafadede84f3afc96da2e72084cae3f988464644aec4f392eb9e823'


def copy(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    require(not destination.exists(),'PACKAGE_COPY_WOULD_OVERWRITE')
    shutil.copyfile(source,destination)


def model_assets(folder, adapter, handoff):
    for name in ('adapter_config.json','adapter_model.safetensors'):
        copy(adapter/name,folder/'adapter'/name)
    reference=read_json(handoff/'data/pilot-v2/tokenizer-reference.json')
    for name,info in reference['files'].items():
        require(sha_file(handoff/'tokenizer'/name)==info['sha256'],'SOURCE_TOKENIZER_PIN')
        copy(handoff/'tokenizer'/name,folder/'tokenizer'/name)
    copy(handoff/'data/pilot-v2/tokenizer-reference.json',folder/'tokenizer-reference.json')
    config=dict(schema_version='comparison-runner-v1',stage='DEV_ONLY',main_authorized=False,
        model_id=MODEL,model_revision=REVISION,adapter_sha256=PILOT_SHA,
        adapter_config_sha256=sha_file(adapter/'adapter_config.json'),generation=dict(LIMITS),
        attempts=1,warmup_calls_per_arm=2,selected_adapter='original_pilot_50_updates',
        quantization='NF4_DOUBLE_QUANT_FP16',history=False,response_cache=False,repair=False,retries=False)
    require(sha_file(adapter/'adapter_model.safetensors')==PILOT_SHA,'ORIGINAL_PILOT_ADAPTER_REQUIRED')
    return config


def make_notebook(path, zip_path, zip_hash):
    import hashlib
    with ZipFile(zip_path) as archive:
        transport_hash=hashlib.sha256(archive.read('bundle-manifest.json')).hexdigest()
    def code(text):
        return dict(cell_type='code',execution_count=None,metadata={},outputs=[],source=text.splitlines(keepends=True))
    bootstrap = '''from pathlib import Path
import hashlib, json, os, stat, zipfile, subprocess, sys, time
from datetime import datetime, timezone
os.environ.update(CUDA_VISIBLE_DEVICES='0', USE_TF='0', USE_FLAX='0', PYTHONDONTWRITEBYTECODE='1', TOKENIZERS_PARALLELISM='false')
EXPECTED = ZIP_HASH
EXPECTED_TRANSPORT = TRANSPORT_HASH
matches = [p for p in Path('/kaggle/input').rglob('runner-dev.zip') if hashlib.sha256(p.read_bytes()).hexdigest() == EXPECTED]
PACKAGE = Path('/kaggle/working/comparison-package-' + EXPECTED[:12])
if matches:
    assert len(matches) == 1, 'Duplicate matching ZIP inputs.'
    with zipfile.ZipFile(matches[0]) as z:
        names = z.namelist()
        assert len(names) == len(set(names))
        transport = z.read('bundle-manifest.json')
        assert hashlib.sha256(transport).hexdigest() == EXPECTED_TRANSPORT
        manifest = json.loads(transport)
        assert set(names) == set(manifest) | {'bundle-manifest.json'}
        assert all(not stat.S_ISLNK(i.external_attr >> 16) for i in z.infolist())
        payload = {name: z.read(name) for name in manifest}
else:
    manifests = [p for p in Path('/kaggle/input').rglob('bundle-manifest.json') if hashlib.sha256(p.read_bytes()).hexdigest() == EXPECTED_TRANSPORT]
    assert len(manifests) == 1, 'Add the exact runner-dev ZIP or its extracted Kaggle Dataset.'
    source = manifests[0].parent.resolve()
    manifest = json.loads(manifests[0].read_text())
    payload = {}
    for name in manifest:
        p = (source / name).resolve()
        assert p.is_relative_to(source) and not (source / name).is_symlink()
        payload[name] = p.read_bytes()
for name, raw in payload.items():
    target = (PACKAGE / name).resolve()
    assert target.is_relative_to(PACKAGE.resolve()) and not Path(name).is_absolute()
    assert chr(92) not in name and ':' not in name
    assert len(raw) == manifest[name]['bytes'] and hashlib.sha256(raw).hexdigest() == manifest[name]['sha256']
for name, raw in payload.items():
    target = PACKAGE / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert hashlib.sha256(target.read_bytes()).hexdigest() == manifest[name]['sha256']
    else:
        with target.open('xb') as f: f.write(raw)
PYTHON = Path('/kaggle/working/comparison-env/bin/python')
print('Package authenticated. Main locked. Qwen weights not loaded.')
'''.replace('ZIP_HASH',repr(zip_hash)).replace('TRANSPORT_HASH',repr(transport_hash))
    setup = '''subprocess.run([sys.executable, '-B', '-m', 'scripts.comparison.kaggle', '--package', str(PACKAGE)], cwd=PACKAGE, check=True)
print('Environment/assets checked. Smoke/dev Qwen has not run yet.')
'''
    # Export outside the package/run directory, retaining raw outputs and failures.
    common = '''def execute(mode):
    run = Path('/kaggle/working/comparison-runs') / (mode + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    run.parent.mkdir(parents=True, exist_ok=True)
    console = Path(str(run) + '-console.log')
    started = time.monotonic()
    with console.open('x', encoding='utf-8') as log:
        process = subprocess.Popen([str(PYTHON), '-B', '-m', 'scripts.comparison.runner', '--package', str(PACKAGE), '--output', str(run), '--mode', mode], cwd=PACKAGE, stdout=log, stderr=subprocess.STDOUT)
        while process.poll() is None:
            try:
                progress = json.loads((run / 'progress.json').read_text())
            except (OSError, json.JSONDecodeError):
                progress = dict(phase='STARTING', rows=0)
            print(str(int(time.monotonic()-started)) + 's | ' + json.dumps(progress), flush=True)
            time.sleep(15)
    audit = json.loads((run / 'audit.json').read_text()) if (run / 'audit.json').exists() else None
    archive = Path(str(run) + '.zip')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        z.write(console, 'console.log')
        for p in sorted(run.rglob('*')):
            if p.is_file(): z.write(p, p.relative_to(run).as_posix())
    receipt = dict(archive=archive.name, sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), size_bytes=archive.stat().st_size, process_exit_code=process.returncode, audit=audit)
    receipt_path = Path(str(run) + '-receipt.json')
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    print('ZIP:', archive, '\\nReceipt:', receipt_path, '\\nAudit:', run / 'audit.json')
    assert process.returncode == 0 and audit is not None, 'Run incomplete; the ZIP and receipt preserve available failure evidence.'
    return run, audit
SMOKE_RUN, SMOKE_AUDIT = execute('smoke')
'''
    dev = '''assert SMOKE_AUDIT['rows'] == 3 and SMOKE_AUDIT['failure_rows'] == 0, 'Resolve smoke failures before dev.'
DEV_RUN, DEV_AUDIT = execute('dev')
'''
    notebook=dict(nbformat=4,nbformat_minor=5,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3')),
        cells=[dict(cell_type='markdown',metadata={},source=['# So sánh ba nhánh: smoke và dev\n','T4, Internet bật; Input là ZIP đúng checksum. Không chạy training hoặc main.\n']),
               code(bootstrap),code(setup),code(common),code(dev)])
    if path is None:
        return notebook
    path.parent.mkdir(parents=True,exist_ok=True)
    require(not path.exists(),'NOTEBOOK_ALREADY_EXISTS')
    path.write_text(json.dumps(notebook,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def build(retrieval,output,adapter,handoff):
    require(output.resolve().is_relative_to(ROOT/'.private') and not output.exists(),'NEW_PRIVATE_PACKAGE_REQUIRED')
    complete=read_json(retrieval/'complete.json')
    verify_inventory(retrieval,complete['files'])
    require(set(inventory(retrieval,('complete.json',)))==set(complete['files']),'PREPARATION_FILE_SET')
    readiness=read_json(ROOT/'.private/comparison/experiment-readiness.json')
    require(readiness['split_counts']==dict(train=770,validation=114,instruction_holdout=116),'CURRENT_TRAINING_SELECTION')
    train=ROOT/readiness['training_path']
    require(sha_file(train/'manifest.json')==readiness['normalized_training_manifest_sha256'],'TRAINING_MANIFEST_BINDING')
    verify_inventory(train,read_json(train/'manifest.json')['files'])
    output.mkdir(parents=True)
    contents=output/'contents'
    config=model_assets(contents,adapter,handoff)
    require(sha_file(adapter.parent/'checkpoint-50/adapter_model.safetensors')==PILOT_SHA,'PILOT_FINAL_CHECKPOINT_50_DIFFERENCE')
    config.update(training_manifest_sha256=readiness['normalized_training_manifest_sha256'],
                  retrieval_complete_sha256=sha_file(retrieval/'complete.json'),
                  benchmark_manifest_sha256=readiness['benchmark_manifest_sha256'])
    write_json(contents/'run-config.json',config)
    files=['scripts/comparison/'+n for n in ('__init__.py','runner.py','packing.py','protocol.py','kaggle.py','requirements.txt')]
    files += ['scripts/qlora/'+n for n in ('__init__.py','data.py','runtime.py','requirements.txt')]
    files += ['data/comparison/'+n for n in ('base-system.txt','rag-system.txt','input.schema.json','output.schema.json')]
    for name in files:
        copy(ROOT/name,contents/name)
    for suffix in ('inputs.jsonl','cache.jsonl','model-inputs.jsonl','schedule.json'):
        copy(retrieval/('dev.'+suffix),contents/'inputs'/('dev.'+suffix))
    write_json(contents/'manifest.json',dict(files=inventory(contents)))
    tokenizer,model_report=audit_assets(contents,config)
    validate_config(config,'dev')
    inputs,caches,models=[read_rows(contents/'inputs'/('dev.'+n+'.jsonl')) for n in ('inputs','cache','model-inputs')]
    validate_inputs(inputs,caches,models,tokenizer)
    require(read_json(contents/'inputs/dev.schedule.json')==schedule(inputs),'DEV_SCHEDULE')
    require(len(inputs)==30 and len(models)==90,'DEV_COUNTS')
    for name in inventory(contents):
        require(not any(part in name.lower() for part in ('.references.jsonl','evaluator','metadata.jsonl','holdout','train.jsonl','reviews.csv','semantic-findings')),'GENERATOR_CONTAINS_PRIVATE_LABELS')
    archive=output/'runner-dev.zip'
    receipt=write_bundle(contents,archive)
    # The package manifest and the transport manifest deliberately serve separate roles.
    verify_bundle(archive)
    write_json(output/'preflight.json',dict(status='DEV_RUNNER_PACKAGE_READY_GPU_SMOKE_NOT_RUN',
        assets=model_report,dev_cases=30,model_input_rows=90,main_packaged=False,training_packaged=False,
        labels_packaged=False,adapter_runtime_reload='PENDING_STEP_4',zip_sha256=receipt['zip_sha256']))
    make_notebook(ROOT/'notebooks/comparison.ipynb',archive,receipt['zip_sha256'])
    print(json.dumps(read_json(output/'preflight.json'),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrieval',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--adapter',type=Path,default=ROOT/'.private/qlora/runs/pilot-20261104T180615021055Z/final-adapter')
    parser.add_argument('--handoff',type=Path,default=ROOT/'.private/qlora/inputs/handoff')
    parser.add_argument('--assets-only',action='store_true')
    args=parser.parse_args()
    if args.assets_only:
        require(args.output.resolve().is_relative_to(ROOT/'.private') and not args.output.exists(),'NEW_PRIVATE_ASSET_OUTPUT')
        config=model_assets(args.output,args.adapter,args.handoff)
        _,report=audit_assets(args.output,config)
        write_json(args.output/'run-config.json',config)
        write_json(args.output/'preflight.json',report)
        write_json(args.output/'manifest.json',dict(files=inventory(args.output)))
        print(json.dumps(report,indent=2))
    else:
        build(args.retrieval,args.output,args.adapter,args.handoff)
