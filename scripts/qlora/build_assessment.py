"""Build a self-contained verification notebook without altering the accepted trainer."""
import copy
import hashlib
import json
from pathlib import Path

from .assessment import PILOT_NAME, PILOT_SHA
from .data import read_json, require, sha_file


def main():
    root = Path(__file__).resolve().parents[2]
    pilot = root / '.private/qlora/runs' / PILOT_NAME
    require(sha_file(pilot / 'run-manifest.json') == PILOT_SHA, 'ACCEPTED_PILOT_REQUIRED')
    manifest = read_json(pilot / 'run-manifest.json')
    frozen = {name: (pilot / 'source/qlora' / name).read_bytes().decode('utf-8')
              for name in manifest['source_files_sha256']}
    require(all(hashlib.sha256(text.encode()).hexdigest() == manifest['source_files_sha256'][name]
                for name, text in frozen.items()), 'FROZEN_SOURCE_INTEGRITY')
    names = ('data.py', 'collator.py', 'runtime.py', 'train.py', 'storage.py', 'smoke.py', 'pilot.py')
    for name in names:
        require(frozen[name] == (Path(__file__).parent / name).read_text(encoding='utf-8'),
                'REVIEWED_TRAINER_CHANGED:' + name)
    sources = {name: (Path(__file__).parent / name).read_text(encoding='utf-8')
               for name in names + ('assessment.py',)}
    source_id = hashlib.sha256(json.dumps(sources, sort_keys=True, ensure_ascii=False,
                                          separators=(',', ':')).encode()).hexdigest()
    notebook = read_json(root / 'notebooks/qlora_pilot.ipynb')
    notebook['cells'] = copy.deepcopy(notebook['cells'][:4])
    setup = '''# Reload the saved adapter and compare exactly 20 locked development cases.
import os, time
assert json.loads((REPORT / 'environment-check.json').read_text())['status'] == 'ENVIRONMENT_READY_FOR_SMOKE'
for name in ('SMOKE_PROCESS', 'PILOT_PROCESS', 'VERIFY_PROCESS'):
    previous = globals().get(name)
    if previous is not None and previous.poll() is None:
        raise RuntimeError('A GPU process is already running.')
VERIFY_SOURCES = __SOURCES__
VERIFY_SOURCE_ID = '__SOURCE_ID__'
assert hashlib.sha256(json.dumps(VERIFY_SOURCES, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == VERIFY_SOURCE_ID
VERIFY_TOOLS = WORK / ('tools-assessment-' + VERIFY_SOURCE_ID[:12])
if not VERIFY_TOOLS.exists():
    shutil.copytree(RUN_TOOLS, VERIFY_TOOLS)
    for name, content in VERIFY_SOURCES.items():
        (VERIFY_TOOLS / 'scripts/qlora' / name).write_bytes(content.encode())
expected = {p.relative_to(RUN_TOOLS).as_posix() for p in RUN_TOOLS.rglob('*') if p.is_file()} | {'scripts/qlora/' + name for name in VERIFY_SOURCES}
assert {p.relative_to(VERIFY_TOOLS).as_posix() for p in VERIFY_TOOLS.rglob('*') if p.is_file()} == expected
for name in expected:
    content = VERIFY_SOURCES.get(Path(name).name) if name.startswith('scripts/qlora/') else None
    assert (VERIFY_TOOLS / name).read_bytes() == (content.encode() if content is not None else (RUN_TOOLS / name).read_bytes())
FROZEN_SOURCES = __FROZEN__
FROZEN_HASHES = __FROZEN_HASHES__
FROZEN_TOOLS = WORK / 'tools-pilot-frozen-b228645e1df2'
frozen_files = {'scripts/__init__.py': b'', 'configs/qlora-pilot.json': __RECIPE__}
for name, content in FROZEN_SOURCES.items():
    assert hashlib.sha256(content.encode()).hexdigest() == FROZEN_HASHES[name]
    frozen_files['scripts/qlora/' + name] = content.encode()
if not FROZEN_TOOLS.exists():
    for name, content in frozen_files.items():
        path = FROZEN_TOOLS / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
assert {p.relative_to(FROZEN_TOOLS).as_posix() for p in FROZEN_TOOLS.rglob('*') if p.is_file()} == set(frozen_files)
for name, content in frozen_files.items():
    assert (FROZEN_TOOLS / name).read_bytes() == content, 'FROZEN_RUNTIME_CHANGED'
VERIFY_DIR = WORK / 'verification' / ('verification-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
BASE_CACHE = WORK / 'base-cache'
VERIFY_ENV = dict(os.environ, CUDA_VISIBLE_DEVICES='0', USE_TF='0', USE_FLAX='0', PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', TOKENIZERS_PARALLELISM='false', HF_HUB_OFFLINE='0', TRANSFORMERS_OFFLINE='0', HF_XET_CHUNK_CACHE_SIZE_BYTES='0', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
PYTHON = str(VENV / 'bin/python')
subprocess.run([PYTHON, '-B', '-m', 'scripts.qlora.assessment', '--stage', 'prepare', '--output', str(VERIFY_DIR), '--work', str(WORK), '--bundle', str(HANDOFF), '--frozen-tools', str(FROZEN_TOOLS)], cwd=VERIFY_TOOLS, env=VERIFY_ENV, check=True)

def run_verified_process(command, cwd, label, phase_path):
    global VERIFY_PROCESS
    if 'VERIFY_PROCESS' in globals() and VERIFY_PROCESS.poll() is None:
        raise RuntimeError('A verification process is already running.')
    stdout_path = VERIFY_DIR / (label + '-stdout.txt')
    stderr_path = VERIFY_DIR / (label + '-stderr.txt')
    with stdout_path.open('x', encoding='utf-8') as stdout, stderr_path.open('x', encoding='utf-8') as stderr:
        VERIFY_PROCESS = subprocess.Popen(command, cwd=cwd, env=VERIFY_ENV, stdout=stdout, stderr=stderr)
        started = time.monotonic()
        try:
            while VERIFY_PROCESS.poll() is None:
                try:
                    phase = json.loads(phase_path.read_text())
                except (FileNotFoundError, ValueError):
                    phase = {}
                print(f"{label}: {int(time.monotonic() - started)}s | {phase.get('phase', 'LOADING_OR_VALIDATING')} | completed={phase.get('completed', '-')} | step={phase.get('step', '-')}", flush=True)
                time.sleep(15)
        except BaseException:
            VERIFY_PROCESS.terminate()
            try:
                VERIFY_PROCESS.wait(timeout=30)
            except subprocess.TimeoutExpired:
                VERIFY_PROCESS.kill()
                VERIFY_PROCESS.wait()
            raise
    if VERIFY_PROCESS.returncode != 0:
        print(stderr_path.read_text(encoding='utf-8')[-5000:])
        raise RuntimeError(label + ' failed. Keep this run and send the error; do not overwrite it.')
    print(stdout_path.read_text(encoding='utf-8')[-2000:])

print('Reload + comparison: 20 cases x 2 arms, plus 2 untimed warmup calls. No training in this cell.')
print('Output:', VERIFY_DIR)
run_verified_process([PYTHON, '-B', '-m', 'scripts.qlora.assessment', '--stage', 'evaluate', '--output', str(VERIFY_DIR), '--cache-dir', str(BASE_CACHE), '--allow-model-download'], VERIFY_TOOLS, 'evaluation', VERIFY_DIR / 'phase.json')
'''
    setup = setup.replace('__SOURCES__', repr(sources)).replace('__SOURCE_ID__', source_id)
    setup = setup.replace('__FROZEN__', repr(frozen)).replace('__FROZEN_HASHES__', repr(manifest['source_files_sha256']))
    setup = setup.replace('__RECIPE__', repr((root / 'configs/qlora-pilot.json').read_bytes()))
    resume = '''# Verify checkpoint resume in a NEW process. Exactly one optimizer update: 25 -> 26.
assert (VERIFY_DIR / 'evaluation/comparison.json').is_file(), 'Run reload/comparison first.'
context = json.loads((VERIFY_DIR / 'context.json').read_text())
PILOT_RUN = Path(context['pilot'])
print('Resume verification: 25 -> 26 only. max_steps remains 50 to preserve the original scheduler.')
run_verified_process([PYTHON, '-B', '-m', 'scripts.qlora.train', '--bundle', str(HANDOFF), '--config', str(FROZEN_TOOLS / 'configs/qlora-pilot.json'), '--profile', 'pilot', '--output', str(VERIFY_DIR / 'resume'), '--cache-dir', str(BASE_CACHE), '--allow-model-download', '--resume-from-checkpoint', str(PILOT_RUN / 'checkpoint-25'), '--resume-manifest-sha256', context['pilot_manifest_sha256'], '--stop-after-step', '26'], FROZEN_TOOLS, 'resume', VERIFY_DIR / 'resume/phase.json')
'''
    export = '''# CPU artifact audit and private export. Does not run training or generation.
assert VERIFY_PROCESS.returncode == 0 and (VERIFY_DIR / 'resume/run-manifest.json').is_file()
subprocess.run([PYTHON, '-B', '-m', 'scripts.qlora.assessment', '--stage', 'export', '--output', str(VERIFY_DIR)], cwd=VERIFY_TOOLS, env=VERIFY_ENV, check=True)
print(VERIFY_DIR.with_name(VERIFY_DIR.name + '-audit.json').read_text(encoding='utf-8'))
print('Send verification ZIP, audit JSON and receipt. Semantic scores remain blank for content review.')
'''
    for id_, text in (('reload-comparison', setup), ('resume-verification', resume), ('verification-evidence', export)):
        compile(text, id_, 'exec')
        notebook['cells'].append(dict(cell_type='code', id=id_, metadata={}, execution_count=None,
                                      outputs=[], source=text.splitlines(keepends=True)))
    notebook['cells'][0]['source'] = [
        '# OHAYO - QLoRA Verification\n',
        'Code cell 1-3: Input/moi truong. Cell 4: reload adapter va so sanh 20 ca (40 dau ra). Cell 5: resume 25 -> 26 dung 1 update. Cell 6: audit + ZIP. Khong train lai pilot 50.\n',
        'Giu phien/Input/cache hien tai, GPU T4 va Internet. Neu mat phien, them ZIP pilot goc vao mot Dataset Private/Input; khong upload base-cache. Khong chay cung inference server.\n',
        'Ket qua 20 ca chi la development, khong phai holdout. Format/citation ID/lexical overlap khong thay cham dung noi dung va bam nguon.\n']
    notebook['metadata'].pop('ohayo_gpu_pilot', None)
    notebook['metadata']['ohayo_gpu_verification'] = dict(source_id=source_id,
        pilot_manifest_sha256=PILOT_SHA, frozen_trainer_sources=manifest['source_files_sha256'],
        development_cases=20, inference_outputs=40, resume_start=25, resume_stop=26,
        original_scheduler_steps=50, gpu_execution='REQUIRES_USER_KAGGLE_RUN')
    path = root / 'notebooks/qlora_verification.ipynb'
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('Verification notebook updated: ' + path.name)


if __name__ == '__main__':
    main()
