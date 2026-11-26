"""Package the frozen serving Input and paired evaluation runner without training data."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from scripts.serving_comparison import build_cases

ROOT = Path(__file__).resolve().parents[1]

SETUP = '''from pathlib import Path
import hashlib, json, os, zipfile, subprocess, sys
from datetime import datetime, timezone
os.environ.update(TOKENIZERS_PARALLELISM='false', USE_TF='0', USE_FLAX='0', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
if globals().get('_ohayo_service'):
    raise RuntimeError('Restart Python first; do not run beside a loaded serving model.')
EXPECTED = __HASH__
PAYLOAD_HASHES = __PAYLOAD_HASHES__
SERVING_MANIFEST_SHA256 = __SERVING_MANIFEST_HASH__
WORK = Path('/kaggle/working/ayo-paired-' + EXPECTED[:12])

def restore_expanded_serving(root):
    manifests = [p for p in root.rglob('manifest.json') if p.is_file() and not p.is_symlink()
                 and hashlib.sha256(p.read_bytes()).hexdigest()==SERVING_MANIFEST_SHA256]
    if not manifests:
        raise RuntimeError('Serving ZIP and matching expanded serving manifest are both missing from this Input.')
    source = manifests[0].parent.resolve()
    manifest_bytes = manifests[0].read_bytes()
    inventory = json.loads(manifest_bytes)['files']
    if len(inventory)>100 or sum(info['size_bytes'] for info in inventory.values())>160*1024**2:
        raise RuntimeError('Oversized expanded serving Input')
    contents = {'manifest.json':manifest_bytes}
    for name, info in inventory.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or ':' in name or chr(92) in name:
            raise RuntimeError('Unsafe expanded serving path')
        path = source/relative
        if path.is_symlink() or not path.resolve().is_relative_to(source) or not path.is_file():
            raise RuntimeError('Missing or unsafe expanded serving file: '+name)
        data = path.read_bytes()
        if len(data)!=info['size_bytes'] or hashlib.sha256(data).hexdigest()!=info['sha256']:
            raise RuntimeError('Expanded serving checksum changed: '+name)
        contents[name] = data
    return contents

expanded_serving = None
inputs = [p for p in Path('/kaggle/input').rglob('comparison-input.zip') if hashlib.sha256(p.read_bytes()).hexdigest()==EXPECTED]
if inputs:
    with zipfile.ZipFile(inputs[0]) as archive:
        if set(archive.namelist()) != set(PAYLOAD_HASHES) or len(archive.namelist())!=3:
            raise RuntimeError('Wrong comparison package inventory')
        if sum(i.file_size for i in archive.infolist()) > 180*1024**2:
            raise RuntimeError('Oversized Input')
        payloads = {name:archive.read(name) for name in archive.namelist()}
else:
    roots = [p.parent for p in Path('/kaggle/input').rglob('runner.py')
             if hashlib.sha256(p.read_bytes()).hexdigest()==PAYLOAD_HASHES['runner.py']]
    if not roots:
        raise RuntimeError('Attach comparison-input.zip as a private dataset; keep the NF4 checkpoint Input.')
    payloads = {}
    for name in PAYLOAD_HASHES:
        path = roots[0]/name
        if path.is_symlink() or not path.resolve().is_relative_to(roots[0].resolve()):
            raise RuntimeError('Unsafe extracted Input')
        if name=='serving-input.zip' and not path.exists():
            expanded_serving = restore_expanded_serving(roots[0])
        elif path.is_file():
            payloads[name] = path.read_bytes()
        else:
            raise RuntimeError('Missing comparison Input file: '+name)
WORK.mkdir(exist_ok=True)
for name, data in payloads.items():
    if hashlib.sha256(data).hexdigest()!=PAYLOAD_HASHES[name]:
        raise RuntimeError('Comparison payload checksum changed')
    path = WORK/name
    if path.is_symlink() or (path.exists() and path.read_bytes()!=data):
        raise RuntimeError('Existing comparison package changed')
    path.write_bytes(data)
if expanded_serving is not None:
    expanded_root = WORK/'serving-expanded'
    for name,data in expanded_serving.items():
        path = expanded_root/name
        if path.is_symlink() or not path.resolve().is_relative_to(expanded_root.resolve()):
            raise RuntimeError('Unsafe serving staging destination')
        if path.exists() and path.read_bytes()!=data:
            raise RuntimeError('Existing expanded serving package changed')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    print('SERVING_INPUT_VERIFIED: expanded manifest and every file checksum; original ZIP not required.')
del payloads
RUN = WORK / ('results-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
RUN.mkdir()
print('INPUT_VERIFIED:', WORK)
print('Requests per arm:', len(json.loads((WORK/'cases.json').read_bytes())['requests']))
'''

ENVIRONMENT = '''import importlib.metadata
from packaging.specifiers import SpecifierSet
requirements = {'transformers':'==4.57.6','tokenizers':'==0.22.2','bitsandbytes':'==0.48.2',
                'accelerate':'==1.15.0','peft':'==0.17.1','safetensors':'==0.8.0','lm-format-enforcer':'==0.11.3'}
missing = []
for name, constraint in requirements.items():
    try:
        valid = importlib.metadata.version(name) in SpecifierSet(constraint)
    except importlib.metadata.PackageNotFoundError:
        valid = False
    if not valid:
        missing.append(name+constraint)
if missing:
    subprocess.run([sys.executable,'-m','pip','install',*missing],check=True)
subprocess.run([sys.executable,'-c',
    'import torch,peft,bitsandbytes; from transformers import AutoTokenizer; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))'],check=True)
dependencies = {name:importlib.metadata.version(name) for name in ['torch',*requirements]}
(RUN/'dependencies.json').write_text(json.dumps(dependencies,indent=2))
print('ENVIRONMENT_READY; no model loaded in this kernel, no training.')
'''

EXECUTE = '''import time
failures = []
for arm in ('base_rag','tuned_rag'):
    command = [sys.executable,'-u',str(WORK/'runner.py'),'--package',str(SERVING_PACKAGE),
               '--arm',arm,'--cases',str(WORK/'cases.json'),'--output',str(RUN/arm)]
    log = RUN/(arm+'.log')
    with log.open('w') as stream:
        process = subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT)
        started = time.monotonic()
        while process.poll() is None:
            time.sleep(15)
            lines = log.read_text(errors='replace').splitlines()
            print(arm, round(time.monotonic()-started), 's |', lines[-1][-240:] if lines else 'STARTING',flush=True)
    if process.returncode:
        failures.append(arm)
        print('RUN_FAILED:',arm,'| evidence preserved; do not train again.')
if not failures:
    subprocess.run([sys.executable,str(WORK/'runner.py'),'--audit','--cases',str(WORK/'cases.json'),
                    '--output',str(RUN)],check=True)
else:
    (RUN/'failure.json').write_text(json.dumps({'failed_arms':failures}))
print('Run cell 4 to export all evidence, including failures. Backend configuration unchanged.')
'''

EXPORT = '''from IPython.display import FileLink, display
archive_path = WORK/(RUN.name+'.zip')
with zipfile.ZipFile(archive_path,'x',zipfile.ZIP_DEFLATED) as archive:
    archive.write(WORK/'cases.json','cases.json')
    for path in sorted(RUN.rglob('*')):
        if path.is_file() and 'source' not in path.relative_to(RUN).parts:
            archive.write(path,path.relative_to(RUN).as_posix())
receipt = dict(sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest(),size_bytes=archive_path.stat().st_size,
               comparison_input_sha256=EXPECTED,serving_input_sha256=EXPECTED_PACKAGE_SHA256)
receipt_path = archive_path.with_suffix('.receipt.json')
receipt_path.write_text(json.dumps(receipt,indent=2))
display(FileLink(str(archive_path)),FileLink(str(receipt_path)))
print('Send ZIP + receipt. Semantic review and model selection follow; no training performed.')
'''


def build(*, output=None, serving_directory=None, notebook_path=None):
    from scripts.package_adapter_serving import CELL_INPUT
    from scripts.guardrails_preflight import verify
    verify(ROOT/'.private/guardrails/baseline')
    directory = Path(output) if output is not None else ROOT/'.private/guardrails/comparison'
    directory.mkdir(parents=True, exist_ok=True)
    serving = Path(serving_directory) if serving_directory is not None else ROOT/'.private/guardrails/serving'
    receipt = json.loads((serving/'receipt.json').read_bytes())
    original = (serving/'serving-input.zip').read_bytes()
    if hashlib.sha256(original).hexdigest() != receipt['package_sha256']:
        raise ValueError('Serving Input checksum changed')
    with ZipFile(serving/'serving-input.zip') as archive:
        manifest_bytes = archive.read('manifest.json')
    plan = json.loads((ROOT/'data/qa/guardrails-cases.json').read_bytes())
    cases = build_cases(plan, ROOT/plan['fixture'])
    payloads = {'serving-input.zip':original, 'runner.py':(ROOT/'scripts/serving_comparison.py').read_bytes(),
                'cases.json':json.dumps(cases,ensure_ascii=False,indent=2).encode()}
    target = directory/'comparison-input.zip'
    with ZipFile(target,'w',ZIP_DEFLATED) as archive:
        for name, data in sorted(payloads.items()):
            info = ZipInfo(name, date_time=(1980,1,1,0,0,0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info,data)
    package_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    extraction = CELL_INPUT.replace('__PACKAGE_HASH__',repr(receipt['package_sha256']))
    extraction = extraction.replace('__MANIFEST_HASH__',repr(hashlib.sha256(manifest_bytes).hexdigest()))
    extraction = extraction.replace('__ADAPTER_HASH__',repr(receipt['adapter_sha256']))
    extraction = extraction.replace("Path('/kaggle/input').rglob", "WORK.rglob")
    setup = SETUP.replace('__HASH__',repr(package_hash)).replace('__PAYLOAD_HASHES__',
        repr({name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}))
    setup = setup.replace('__SERVING_MANIFEST_HASH__',repr(hashlib.sha256(manifest_bytes).hexdigest()))
    first = setup+'\n'+extraction
    notebook = dict(nbformat=4,nbformat_minor=5,metadata=dict(kernelspec=dict(
        display_name='Python 3',language='python',name='python3')), cells=[])
    notebook['cells'].append(dict(cell_type='markdown',id='guide',metadata={},source=[
        '# OHAYO - Serving Comparison\n\nFresh kernel, GPU T4, Internet. Attach the private comparison Input and existing NF4 checkpoint. Run cells 1-4. Both arms run sequentially in isolated processes on the same GPU. No Secrets, tunnel, training or backend changes. Export even if a run fails.\n']))
    for name, source in [('input',first),('environment',ENVIRONMENT),('compare',EXECUTE),('export',EXPORT)]:
        compile(source,name,'exec')
        notebook['cells'].append(dict(cell_type='code',id=name,metadata={},execution_count=None,
                                     outputs=[],source=source.splitlines(keepends=True)))
    path = Path(notebook_path) if notebook_path is not None else ROOT/'notebooks/ayo_comparison.ipynb'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    output = dict(status='PREPARED_GPU_EXECUTION_PENDING',package_sha256=package_hash,
        size_bytes=target.stat().st_size,requests_per_arm=len(cases['requests']),
        serving_package_sha256=receipt['package_sha256'],
        notebook_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (directory/'receipt.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(output,indent=2))
    return target, path


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--serving-directory', type=Path)
    parser.add_argument('--notebook', type=Path)
    args = parser.parse_args()
    build(output=args.output, serving_directory=args.serving_directory, notebook_path=args.notebook)
