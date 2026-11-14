"""Prepare a private 770/114 training package only after smoke/dev readback."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
from zipfile import ZipFile

from scripts.comparison.package_runner import copy, make_notebook
from scripts.comparison.protocol import read_rows, verify_bundle, write_bundle, write_json
from scripts.comparison.runner import audit_outputs
from scripts.comparison.training import COUNTS, LORA, TRAINING, load_package, validate_config
from scripts.qlora.data import read_json, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory

ROOT=Path(__file__).resolve().parents[2]


def check_generation(archive, package, mode):
    receipt=read_json(archive.with_name(archive.stem+'-receipt.json'))
    require(sha_file(archive)==receipt['sha256'] and archive.stat().st_size==receipt['size_bytes']
            and receipt['process_exit_code']==0,'GENERATION_RECEIPT')
    with ZipFile(archive) as zipped:
        names=zipped.namelist()
        require(len(names)==len(set(names)) and set(names)=={'console.log','audit.json','measurements.jsonl',
            'outputs.jsonl','progress.json','run-plan.json','runtime.json','warmup.jsonl'} and zipped.testzip() is None,'GENERATION_FILES')
        get=lambda name:json.loads(zipped.read(name))
        rows=lambda name:[json.loads(s) for s in zipped.read(name).decode('utf-8').splitlines()]
        plan=get('run-plan.json')
        require(plan['mode']==mode and plan['package_manifest_sha256']==sha_file(package/'manifest.json')
                and plan['config_sha256']==sha_file(package/'run-config.json'),'GENERATION_PACKAGE_BINDING')
        schedule=read_json(package/'inputs/dev.schedule.json')
        if mode=='smoke':
            schedule=schedule[:1]
        require(plan['schedule']==schedule,'GENERATION_SCHEDULE')
        expected=read_rows(package/'inputs/dev.model-inputs.jsonl')
        wanted={r['qa_id'] for r in schedule}
        expected=[r for r in expected if r['qa_id'] in wanted]
        actual=rows('outputs.jsonl')
        config=read_json(package/'run-config.json')
        audited=audit_outputs(expected,actual,config['adapter_sha256'])
        require(audited==get('audit.json')==receipt['audit'] and audited['failure_rows']==0,'GENERATION_AUDIT')
        order=[(s['qa_id'],a) for s in schedule for a in s['arms']]
        require([(r['qa_id'],r['arm']) for r in actual]==order
                and all(r['run_id']==plan['run_id'] for r in actual),'GENERATION_ORDER')
        measurements=rows('measurements.jsonl')
        require([(r['qa_id'],r['arm']) for r in measurements]==order,'GENERATION_MEASUREMENTS')
        require(all(r['adapter_state']['enabled']==(r['arm']=='tuned_rag')
            and r['adapter_state']['layers']==196
            and r['adapter_state']['disabled_layers']==(0 if r['arm']=='tuned_rag' else 196)
            and not r['adapter_state']['merged'] for r in measurements),'GENERATION_ADAPTER_STATE')
        warm=rows('warmup.jsonl')
        require(len(warm)==6 and all(r['status']=='completed' for r in warm)
                and all(sum(r['arm']==arm for r in warm)==2 for arm in ('base','rag','tuned_rag')),'GENERATION_WARMUP')
        runtime=get('runtime.json')
        require(runtime['base_model_id']==config['model_id'] and runtime['base_revision']==config['model_revision']
                and runtime['rows']==len(actual) and runtime['retry_count']==0,'GENERATION_RUNTIME')
        return dict(status='GENERATION_INDEPENDENT_READBACK_PASSED',mode=mode,rows=len(actual),
            archive_sha256=sha_file(archive),package_manifest_sha256=plan['package_manifest_sha256'],
            config_sha256=plan['config_sha256'],factuality='NOT_EVALUATED')


def notebook(path, archive, receipt):
    doc=make_notebook(None,archive,receipt['zip_sha256'])
    bootstrap=''.join(doc['cells'][1]['source']).replace('runner-dev.zip','training-runner.zip')
    bootstrap=bootstrap.replace('comparison-package-','comparison-training-package-').replace('comparison-env/bin/python','comparison-training-env/bin/python')
    bootstrap=bootstrap.replace('Package authenticated. Main locked. Qwen weights not loaded.', 'Training package authenticated: 770 train / 114 validation. Main locked.')
    bootstrap += '\nREQUIRE_EXISTING_SMOKE = True\n'
    helper='''def preserve_training_failure(run, console):
    archive = Path(str(run) + '-failed.zip')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        z.write(console, 'console.log')
        for p in sorted(run.rglob('*')):
            if p.is_file(): z.write(p, p.relative_to(run).as_posix())
    print('Failure evidence:', archive, 'SHA256:', hashlib.sha256(archive.read_bytes()).hexdigest())

def train_run(mode):
    run = Path('/kaggle/working/comparison-training-runs') / (mode + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    run.parent.mkdir(parents=True, exist_ok=True)
    console = Path(str(run) + '-console.log')
    started = time.monotonic()
    with console.open('x', encoding='utf-8') as log:
        process = subprocess.Popen([str(PYTHON), '-B', '-m', 'scripts.comparison.training', '--package', str(PACKAGE), '--output', str(run), '--mode', mode], cwd=PACKAGE, stdout=log, stderr=subprocess.STDOUT)
        while process.poll() is None:
            try:
                phase = json.loads((run / 'phase.json').read_text())
            except (OSError, json.JSONDecodeError):
                phase = dict(phase='STARTING')
            print(str(int(time.monotonic()-started)) + 's | ' + json.dumps(phase), flush=True)
            time.sleep(15)
    if process.returncode:
        preserve_training_failure(run, console)
        raise RuntimeError('Training failed. Send failure ZIP; do not overwrite or retry silently.')
    audited = subprocess.run([str(PYTHON), '-B', '-m', 'scripts.comparison.training_audit', '--run', str(run), '--package', str(PACKAGE)], cwd=PACKAGE)
    if audited.returncode:
        preserve_training_failure(run, console)
        raise RuntimeError('Audit failed. Send failure ZIP; do not train again.')
    audit = json.loads(Path(str(run)+'-audit.json').read_text())
    print(json.dumps(audit, indent=2))
    print('Figures:', run / 'figures')
    return run, audit
OLD_SMOKE = Path('/kaggle/working/comparison-training-runs/smoke-20261112T184520250008Z')
OLD_PACKAGE = Path('/kaggle/working/comparison-training-package-c56f7d302c62')
if OLD_SMOKE.is_dir():
    assert OLD_PACKAGE.is_dir(), 'Keep the old package for authenticated recovery. Do not retrain.'
    expected_old_run = 'd00dc8a4027622cf62f3cd3091dc900baf018e96034f0700c06378e876105aaf'
    assert hashlib.sha256((OLD_SMOKE/'run-manifest.json').read_bytes()).hexdigest() == expected_old_run
    audited = subprocess.run([str(PYTHON), '-B', '-m', 'scripts.comparison.training_audit', '--run', str(OLD_SMOKE), '--package', str(OLD_PACKAGE)], cwd=PACKAGE)
    assert audited.returncode == 0, 'Recovery audit failed. Do not retrain; send output.'
    TRAIN_SMOKE_RUN = OLD_SMOKE
    TRAIN_SMOKE_AUDIT = json.loads(Path(str(OLD_SMOKE)+'-audit.json').read_text())
    print('Existing smoke recovered without training:', json.dumps(TRAIN_SMOKE_AUDIT, indent=2))
else:
    assert not REQUIRE_EXISTING_SMOKE, 'Completed smoke directory missing. Keep the session or restore its authenticated evidence; do not retrain automatically.'
    TRAIN_SMOKE_RUN, TRAIN_SMOKE_AUDIT = train_run('smoke')
'''
    setup="subprocess.run([sys.executable, '-B', '-m', 'scripts.comparison.training_kaggle', '--package', str(PACKAGE)], cwd=PACKAGE, check=True)\n"
    full="assert TRAIN_SMOKE_AUDIT['status'] == 'EXPANDED_TRAINING_SMOKE_PASSED'\nFULL_RUN, FULL_AUDIT = train_run('full')\n"
    devprep='''assert FULL_AUDIT['status'] == 'EXPANDED_ONE_EPOCH_TRAINING_PASSED'
DEV_PACKAGE = Path(str(FULL_RUN) + '-dev-package')
subprocess.run([str(PYTHON), '-B', '-m', 'scripts.comparison.training_audit', '--run', str(FULL_RUN), '--package', str(PACKAGE), '--dev-package', str(DEV_PACKAGE)], cwd=PACKAGE, check=True)
TRAINING_PACKAGE = PACKAGE
PACKAGE = DEV_PACKAGE
'''
    devcalls=''.join(doc['cells'][3]['source'])+"assert SMOKE_AUDIT['failure_rows'] == 0\nDEV_RUN, DEV_AUDIT = execute('dev')\n"
    def code(text):
        return dict(cell_type='code',execution_count=None,metadata={},outputs=[],source=text.splitlines(keepends=True))
    doc['cells']=[dict(cell_type='markdown',metadata={},source=['# QLoRA: huấn luyện mở rộng\n','Một T4, Internet bật. 770 train / 114 validation, không có holdout. Chạy từng cell theo thứ tự; cell 4 chạy một epoch từ base mới, không nối tiếp smoke.\n']),
        code(bootstrap),code(setup),code(helper),code(full),code(devprep+devcalls)]
    require(not path.exists(),'TRAINING_NOTEBOOK_EXISTS')
    path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def build(output, smoke, dev):
    require(output.resolve().is_relative_to(ROOT/'.private') and not output.exists(),'NEW_TRAINING_BUILD_REQUIRED')
    old=ROOT/'.private/comparison/prepared/runner-dev-v1/contents'
    source=ROOT/'.private/comparison/prepared/training-v2'
    manifest=read_json(source/'manifest.json')
    verify_inventory(source,manifest['files'])
    readiness=read_json(ROOT/'.private/comparison/experiment-readiness.json')
    require(sha_file(source/'manifest.json')==readiness['normalized_training_manifest_sha256'],'SELECTED_TRAINING_CHANGED')
    checks={mode:check_generation(path,old,mode) for mode,path in (('smoke',smoke),('dev',dev))}
    output.mkdir(parents=True)
    baselines=output/'baseline'
    baselines.mkdir()
    for path in (smoke,dev):
        for item in (path,path.with_name(path.stem+'-receipt.json')):
            copy(item,baselines/item.name)
    write_json(baselines/'readback.json',checks)
    contents=output/'contents'
    config=read_json(ROOT/'configs/qlora-pilot.json')
    config.update(schema_version='comparison-training-v1',data_manifest_sha256=sha_file(source/'manifest.json'),
        epochs=1,expected_updates=193,counts=COUNTS,holdout_included=False,
        token_limits=read_json(source/'dataset-config.json')['token_limits'],eval_steps=25,save_steps=50,
        initialization='PINNED_BASE_FRESH_LORA',selection='FINAL_EPOCH_NOT_BEST_ON_HOLDOUT',
        original_pilot_sha256=read_json(old/'run-config.json')['adapter_sha256'],main_authorized=False,
        baseline_evidence=checks,rights='DECLARED_NOT_VERIFIED_PRIVATE_RESEARCH_ONLY')
    for key in ('profiles','contract_sha256'):
        config.pop(key,None)
    validate_config(config)
    selection={}
    for split in COUNTS:
        for name in (split+'.jsonl','tokenized-'+split+'.jsonl'):
            copy(source/name,contents/'data'/name)
        selection[split]=[r['record_id'] for r in read_rows(source/('tokenized-'+split+'.jsonl'))]
    write_json(contents/'data/selection.json',dict(splits=selection))
    write_json(contents/'training-config.json',config)
    for name in read_json(old/'tokenizer-reference.json')['files']:
        copy(old/'tokenizer'/name,contents/'tokenizer'/name)
    copy(old/'tokenizer-reference.json',contents/'tokenizer-reference.json')
    for name in ('inputs','cache','model-inputs'):
        copy(old/'inputs'/('dev.'+name+'.jsonl'),contents/'inputs'/('dev.'+name+'.jsonl'))
    copy(old/'inputs/dev.schedule.json',contents/'inputs/dev.schedule.json')
    template=read_json(old/'run-config.json')
    template.update(adapter_sha256=None,adapter_config_sha256=None,selected_adapter='UNSET_UNTIL_TRAINING_AUDIT')
    write_json(contents/'dev-config-template.json',template)
    names=('__init__.py','runner.py','packing.py','protocol.py','training.py','training_audit.py','training_environment.py',
           'training_report.py','training_kaggle.py','training-requirements.txt','requirements.txt')
    files=['scripts/comparison/'+n for n in names]
    files+=['scripts/qlora/'+n for n in ('__init__.py','data.py','collator.py','runtime.py','storage.py','requirements.txt')]
    files+=['data/comparison/'+n for n in ('base-system.txt','rag-system.txt','input.schema.json','output.schema.json')]
    for name in files:
        copy(ROOT/name,contents/name)
    write_json(contents/'manifest.json',dict(files=inventory(contents)))
    data,_,_=load_package(contents)
    archive=output/'training-runner.zip'
    receipt=write_bundle(contents,archive)
    verify_bundle(archive)
    notebook(ROOT/'notebooks/comparison_training.ipynb',archive,receipt)
    write_json(output/'preflight.json',dict(status='EXPANDED_TRAINING_PACKAGE_READY_GPU_NOT_RUN',
        counts={k:len(v) for k,v in data.items()},expected_updates=193,epochs=1,holdout_included=False,
        base_weights_included=False,old_adapter_included=False,charts=list(__import__('scripts.comparison.training_report',fromlist=['FIGURES']).FIGURES),
        baseline_smoke_and_dev=checks,zip_sha256=receipt['zip_sha256'],zip_bytes=receipt['zip_bytes']))
    print(json.dumps(read_json(output/'preflight.json'),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--smoke',type=Path,required=True)
    parser.add_argument('--dev',type=Path,required=True)
    args=parser.parse_args()
    build(args.output,args.smoke,args.dev)
