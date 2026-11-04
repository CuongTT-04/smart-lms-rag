"""Refresh the notebook's reviewed environment overlay without changing locked Input."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[2]
    parser.add_argument('--notebook', type=Path, default=root / 'notebooks/qlora_training.ipynb')
    args = parser.parse_args(argv)
    source = (Path(__file__).parent / 'setup.py').read_text(encoding='utf-8')
    sha = hashlib.sha256(source.encode('utf-8')).hexdigest()
    notebook = json.loads(args.notebook.read_text(encoding='utf-8'))
    # The notebook transports the corrected module as readable Python source.
    # Its source of truth remains setup.py, not a separately maintained fork.
    cell = '''from datetime import datetime, timezone
from importlib.metadata import version
import hashlib, json, os, shutil, subprocess
SINGLE_GPU_ENV = dict(os.environ, CUDA_VISIBLE_DEVICES='0')
VENV = Path('/kaggle/working/qlora-env')
subprocess.run([sys.executable, '-m', 'venv', '--without-pip', '--system-site-packages', str(VENV)], check=True)
subprocess.run([sys.executable, '-m', 'pip', '--python', str(VENV), 'install', '--disable-pip-version-check', 'pip==' + version('pip')], check=True)

# Corrected environment checker, copied into a new runtime tree, not locked Input.
SETUP_SOURCE = __SOURCE__
SETUP_SHA256 = '__SHA__'
assert hashlib.sha256(SETUP_SOURCE.encode('utf-8')).hexdigest() == SETUP_SHA256
ORIGINAL_TOOLS = WORK / 'tools'
RUN_TOOLS = WORK / ('tools-environment-' + SETUP_SHA256[:12])
if not RUN_TOOLS.exists():
    shutil.copytree(ORIGINAL_TOOLS, RUN_TOOLS)
    (RUN_TOOLS / 'scripts/qlora/setup.py').write_bytes(SETUP_SOURCE.encode('utf-8'))
for original in ORIGINAL_TOOLS.rglob('*'):
    if original.is_file():
        relative = original.relative_to(ORIGINAL_TOOLS)
        actual = RUN_TOOLS / relative
        if relative.as_posix() == 'scripts/qlora/setup.py':
            assert hashlib.sha256(actual.read_bytes()).hexdigest() == SETUP_SHA256
        else:
            assert actual.read_bytes() == original.read_bytes(), 'RUNTIME_COPY_DIFFERS'
assert {p.relative_to(RUN_TOOLS).as_posix() for p in RUN_TOOLS.rglob('*') if p.is_file()} == {p.relative_to(ORIGINAL_TOOLS).as_posix() for p in ORIGINAL_TOOLS.rglob('*') if p.is_file()}
TOOLS = RUN_TOOLS
REPORT = WORK / 'reports' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
command = [sys.executable, '-B', '-m', 'scripts.qlora.kaggle', '--bundle', str(HANDOFF), '--profile', 'smoke', '--environment-only', '--output', str(REPORT)]
subprocess.run(command, cwd=TOOLS, env=SINGLE_GPU_ENV, check=True)
'''
    cell = cell.replace('__SOURCE__', repr(source)).replace('__SHA__', sha)
    compile(cell, 'environment-cell', 'exec')
    notebook['cells'][2]['source'] = cell.splitlines(keepends=True)
    notebook['cells'][2]['execution_count'] = None
    notebook['cells'][2]['outputs'] = []
    notebook['metadata']['ohayo_environment_overlay'] = {
        'source': 'scripts/qlora/setup.py', 'sha256': sha,
        'locked_input_modified': False, 'training_storage': 'PENDING_BEFORE_BASE_WEIGHT_LOADING'}
    modules = ('data.py', 'collator.py', 'runtime.py', 'train.py', 'storage.py', 'smoke.py')
    sources = {name: (Path(__file__).parent / name).read_text(encoding='utf-8') for name in modules}
    source_id = hashlib.sha256(json.dumps(sources, ensure_ascii=False, sort_keys=True,
                                          separators=(',', ':')).encode('utf-8')).hexdigest()
    smoke_cell = '''# Step 4: actual Qwen 7B GPU smoke, exactly 2 optimizer steps.
import os, time
assert json.loads((REPORT / 'environment-check.json').read_text())['status'] == 'ENVIRONMENT_READY_FOR_SMOKE'
if 'SMOKE_PROCESS' in globals() and SMOKE_PROCESS.poll() is None:
    raise RuntimeError('A smoke process is already running; do not launch a second one.')
SMOKE_SOURCES = __MODULES__
SMOKE_SOURCE_ID = '__SOURCE_ID__'
assert hashlib.sha256(json.dumps(SMOKE_SOURCES, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest() == SMOKE_SOURCE_ID
BASE_TOOLS = RUN_TOOLS
SMOKE_TOOLS = WORK / ('tools-smoke-' + SMOKE_SOURCE_ID[:12])
if not SMOKE_TOOLS.exists():
    shutil.copytree(BASE_TOOLS, SMOKE_TOOLS)
    for name, content in SMOKE_SOURCES.items():
        (SMOKE_TOOLS / 'scripts/qlora' / name).write_bytes(content.encode('utf-8'))
expected_files = {p.relative_to(BASE_TOOLS).as_posix() for p in BASE_TOOLS.rglob('*') if p.is_file()} | {'scripts/qlora/' + name for name in SMOKE_SOURCES}
assert {p.relative_to(SMOKE_TOOLS).as_posix() for p in SMOKE_TOOLS.rglob('*') if p.is_file()} == expected_files
for relative in expected_files:
    path = SMOKE_TOOLS / relative
    if relative.startswith('scripts/qlora/') and Path(relative).name in SMOKE_SOURCES:
        assert path.read_bytes() == SMOKE_SOURCES[Path(relative).name].encode('utf-8')
    else:
        assert path.read_bytes() == (BASE_TOOLS / relative).read_bytes()
SMOKE_DIR = WORK / 'runs' / ('smoke-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
BASE_CACHE = WORK / 'base-cache'
TRAIN_ENV = dict(os.environ, CUDA_VISIBLE_DEVICES='0', USE_TF='0', USE_FLAX='0', PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', TOKENIZERS_PARALLELISM='false', HF_HUB_OFFLINE='0', TRANSFORMERS_OFFLINE='0', HF_XET_CHUNK_CACHE_SIZE_BYTES='0', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
command = [str(VENV / 'bin/python'), '-B', '-m', 'scripts.qlora.train', '--bundle', str(HANDOFF), '--config', str(SMOKE_TOOLS / 'configs/qlora-pilot.json'), '--profile', 'smoke', '--output', str(SMOKE_DIR), '--cache-dir', str(BASE_CACHE), '--allow-model-download']
print('Smoke: 2 optimizer steps. First run may download base weights; pilot 50 is NOT started.', flush=True)
print('Run:', SMOKE_DIR, flush=True)
SMOKE_PROCESS = subprocess.Popen(command, cwd=SMOKE_TOOLS, env=TRAIN_ENV)
started = time.monotonic()
try:
    while SMOKE_PROCESS.poll() is None:
        phase = {}
        try:
            phase = json.loads((SMOKE_DIR / 'phase.json').read_text())
        except (FileNotFoundError, ValueError):
            pass
        cached = sum(p.stat().st_size for p in BASE_CACHE.rglob('*') if p.is_file() and not p.is_symlink()) if BASE_CACHE.exists() else 0
        step = phase.get('step', '-')
        print(f"{int(time.monotonic() - started)}s | {phase.get('phase', 'STARTING')} | step={step} | cache={cached / 1024**3:.2f} GiB", flush=True)
        time.sleep(15)
except BaseException:
    SMOKE_PROCESS.terminate()
    try:
        SMOKE_PROCESS.wait(timeout=30)
    except subprocess.TimeoutExpired:
        SMOKE_PROCESS.kill()
        SMOKE_PROCESS.wait()
    raise
if SMOKE_PROCESS.returncode != 0:
    for name in ('storage-check.json', 'stderr.txt'):
        path = SMOKE_DIR / name
        if path.exists():
            print(name + ':\\n' + path.read_text(encoding='utf-8')[-6000:])
    raise RuntimeError('Smoke failed; keep this run and send the error output. Do not run pilot.')
print('Training process finished. Run the next cell to audit and export evidence.')
'''
    smoke_cell = smoke_cell.replace('__MODULES__', repr(sources)).replace('__SOURCE_ID__', source_id)
    audit_cell = '''assert SMOKE_PROCESS.returncode == 0, 'Smoke has not completed successfully.'
subprocess.run([str(VENV / 'bin/python'), '-B', '-m', 'scripts.qlora.smoke', '--run', str(SMOKE_DIR)], cwd=SMOKE_TOOLS, env=TRAIN_ENV, check=True)
SMOKE_AUDIT = SMOKE_DIR.with_name(SMOKE_DIR.name + '-audit.json')
print(SMOKE_AUDIT.read_text(encoding='utf-8'))
print('ZIP:', SMOKE_DIR.with_suffix('.zip'))
print('Receipt:', SMOKE_DIR.with_name(SMOKE_DIR.name + '-receipt.json'))
print('Send the audit JSON, ZIP and receipt. Do not run pilot 50 yet.')
'''
    for content in (smoke_cell, audit_cell):
        compile(content, 'smoke-notebook-cell', 'exec')
    notebook['cells'] = [c for c in notebook['cells'] if c.get('id') not in
                         ('smoke-introduction', 'gpu-smoke', 'smoke-evidence')]
    notebook['cells'].extend([
        {'cell_type': 'markdown', 'id': 'smoke-introduction', 'metadata': {}, 'source': [
            '## Buoc 4 - GPU smoke\n',
            'Hai cell tiep theo tai base dung revision (neu chua cache), chay 2 optimizer steps, kiem va dong goi minh chung. Khong chay pilot 50. Chi chay sau khi moi truong dat.\n']},
        {'cell_type': 'code', 'id': 'gpu-smoke', 'metadata': {}, 'execution_count': None,
         'outputs': [], 'source': smoke_cell.splitlines(keepends=True)},
        {'cell_type': 'code', 'id': 'smoke-evidence', 'metadata': {}, 'execution_count': None,
         'outputs': [], 'source': audit_cell.splitlines(keepends=True)}])
    notebook['cells'][0]['source'] = [
        '# OHAYO - QLoRA Training\n',
        'Code cell 1-3: chuan bi/kiem moi truong. Code cell 4-5: GPU smoke 2 optimizer steps va xuat minh chung. Run All luc nay SE chay smoke that, KHONG chay pilot 50.\n',
        'Chon GPU T4, bat Internet, giu Dataset Private qlora-environment-input. Khong can Secret, ngrok, BGE hay checkpoint inference. Khong reset phien sau khi tai base neu con can chay tiep.\n']
    notebook['metadata']['ohayo_gpu_smoke'] = {
        'source_id': source_id, 'max_steps': 2, 'gpu_execution': 'REQUIRES_USER_KAGGLE_RUN',
        'pilot_steps_executed': 0}
    args.notebook.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    # A separate notebook prevents Run All from repeating the accepted smoke.
    import copy
    pilot_notebook = copy.deepcopy(notebook)
    pilot_sources = dict(sources, **{'pilot.py': (Path(__file__).parent / 'pilot.py').read_text(encoding='utf-8')})
    pilot_id = hashlib.sha256(json.dumps(pilot_sources, ensure_ascii=False, sort_keys=True,
                                        separators=(',', ':')).encode('utf-8')).hexdigest()
    pilot_cell = smoke_cell.replace(repr(sources), '__PILOT_MODULE_SOURCES__').replace(source_id, pilot_id)
    pilot_cell = pilot_cell.replace('SMOKE_', 'PILOT_').replace('tools-smoke-', 'tools-pilot-')
    pilot_cell = pilot_cell.replace("'smoke-'", "'pilot-'").replace("'--profile', 'smoke'", "'--profile', 'pilot'")
    pilot_cell = pilot_cell.replace('# Step 4: actual Qwen 7B GPU smoke, exactly 2 optimizer steps.',
                                    '# Step 5: fresh LoRA pilot, exactly 50 optimizer steps; no smoke resume.')
    pilot_cell = pilot_cell.replace('A smoke process', 'A pilot process')
    pilot_cell = pilot_cell.replace('Smoke: 2 optimizer steps. First run may download base weights; pilot 50 is NOT started.',
        'Pilot: 50 optimizer steps, fresh LoRA, checkpoints 25/50. Reuses base-cache; downloads only if missing.')
    pilot_cell = pilot_cell.replace('Smoke failed; keep this run and send the error output. Do not run pilot.',
                                    'Pilot failed; preserve this run and send the error output. Do not overwrite it.')
    pilot_cell = pilot_cell.replace('import os, time\n', '''import os, time
for process_name in ('SMOKE_PROCESS', 'PILOT_PROCESS'):
    previous = globals().get(process_name)
    if previous is not None and previous.poll() is None:
        raise RuntimeError('A training process is already running.')
print('Accepted smoke: 20261104T172418236960Z, 2 applied updates; receiver audit verified locally.')
''')
    pilot_cell = pilot_cell.replace('__PILOT_MODULE_SOURCES__', repr(pilot_sources))
    pilot_audit = audit_cell.replace('SMOKE_', 'PILOT_').replace('scripts.qlora.smoke', 'scripts.qlora.pilot')
    pilot_audit = pilot_audit.replace('Smoke has not completed successfully.', 'Pilot has not completed successfully.')
    pilot_audit = pilot_audit.replace('Send the audit JSON, ZIP and receipt. Do not run pilot 50 yet.',
        'Send the audit JSON, ZIP and receipt. Reload/resume and answer quality are not yet verified.')
    for content in (pilot_cell, pilot_audit):
        compile(content, 'pilot-notebook-cell', 'exec')
    pilot_notebook['cells'] = copy.deepcopy(notebook['cells'][:4]) + [
        {'cell_type': 'markdown', 'id': 'pilot-introduction', 'metadata': {}, 'source': [
            '## Buoc 5 - Pilot QLoRA 50 steps\n',
            'Smoke da duoc tiep nhan va kiem chung. Pilot khoi tao LoRA moi tu base da chot, khong resume smoke. Luu checkpoint 25/50 va final adapter.\n']},
        {'cell_type': 'code', 'id': 'gpu-pilot', 'metadata': {}, 'execution_count': None,
         'outputs': [], 'source': pilot_cell.splitlines(keepends=True)},
        {'cell_type': 'code', 'id': 'pilot-evidence', 'metadata': {}, 'execution_count': None,
         'outputs': [], 'source': pilot_audit.splitlines(keepends=True)}]
    pilot_notebook['cells'][0]['source'] = [
        '# OHAYO - QLoRA Pilot\n',
        'Chay code cell 1-3 de kiem Input/moi truong, cell 4 train 50 steps, cell 5 audit va xuat ZIP. Run All SE huan luyen pilot that, KHONG lap lai smoke.\n',
        'Dung lai Dataset Private hien co va base-cache. Neu session cu con, import notebook trong chinh session do; khong Factory Reset. GPU T4, Internet bat.\n']
    pilot_notebook['metadata'].pop('ohayo_gpu_smoke', None)
    pilot_notebook['metadata']['ohayo_gpu_pilot'] = dict(source_id=pilot_id, max_steps=50,
        gpu_execution='REQUIRES_USER_KAGGLE_RUN', smoke_run='smoke-20261104T172418236960Z',
        smoke_run_manifest_sha256='2e6708182e4030005db5d775eb68647723623d505e8f3951851e84b446f6af40')
    pilot_path = args.notebook.with_name('qlora_pilot.ipynb')
    pilot_path.write_text(json.dumps(pilot_notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('Pilot notebook updated: ' + str(pilot_path))
    print('Notebook environment overlay updated: ' + sha)
    return 0


if __name__ == '__main__':
    sys.exit(main())
