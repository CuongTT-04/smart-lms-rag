"""Build a private inference-only adapter Input and a clean Kaggle notebook."""
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.append_kaggle_dual_gpu import startup_source
from scripts.guardrails_preflight import candidate_identity, verify, PLAN
sys.path.insert(0, str(ROOT / 'backend'))
from apps.ai.providers.adapters import tokenizer_digest


CELL_INPUT = '''from pathlib import Path
import hashlib, json, os, zipfile

ARM = "tuned_rag"  # Rollback: restart Python, set "base_rag", then run cells 1-4.
assert ARM in ("base_rag", "tuned_rag")
if globals().get('_ohayo_service'):
    raise RuntimeError('Restart & Clear Cell Outputs before changing arm or reimporting this notebook.')
EXPECTED_PACKAGE_SHA256 = __PACKAGE_HASH__
EXPECTED_MANIFEST_SHA256 = __MANIFEST_HASH__
EXPECTED_ADAPTER_SHA256 = __ADAPTER_HASH__
candidates = [p for p in Path('/kaggle/input').rglob('serving-input.zip')
              if hashlib.sha256(p.read_bytes()).hexdigest() == EXPECTED_PACKAGE_SHA256]
SERVING_PACKAGE_SHA256 = EXPECTED_PACKAGE_SHA256
SERVING_PACKAGE = Path('/kaggle/working/ayo-serving-' + EXPECTED_PACKAGE_SHA256[:12])
if candidates:
    with zipfile.ZipFile(candidates[0]) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or sum(i.file_size for i in archive.infolist()) > 160 * 1024**2:
            raise RuntimeError('Invalid or oversized serving ZIP')
        payloads = {name:archive.read(name) for name in names}
else:
    manifests = [p for p in Path('/kaggle/input').rglob('manifest.json')
                 if hashlib.sha256(p.read_bytes()).hexdigest() == EXPECTED_MANIFEST_SHA256]
    if not manifests:
        raise RuntimeError('Add the matching private serving Input and keep the NF4 checkpoint Input too.')
    source_root = manifests[0].parent.resolve()
    inventory = json.loads(manifests[0].read_bytes())['files']
    if sum(info['size_bytes'] for info in inventory.values()) > 160 * 1024**2:
        raise RuntimeError('Oversized extracted Input')
    payloads = {'manifest.json':manifests[0].read_bytes()}
    for name in inventory:
        path = source_root / name
        if path.is_symlink() or not path.resolve().is_relative_to(source_root):
            raise RuntimeError('Unsafe extracted Input path')
        payloads[name] = path.read_bytes()
if hashlib.sha256(payloads['manifest.json']).hexdigest() != EXPECTED_MANIFEST_SHA256:
    raise RuntimeError('Serving manifest mismatch')
manifest = json.loads(payloads['manifest.json'])
if set(payloads) != set(manifest['files']) | {'manifest.json'}:
    raise RuntimeError('Unexpected package members')
for name, info in manifest['files'].items():
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts or '\\\\' in name or ':' in name:
        raise RuntimeError('Unsafe package path')
    data = payloads[name]
    if len(data) != info['size_bytes'] or hashlib.sha256(data).hexdigest() != info['sha256']:
        raise RuntimeError('Package checksum mismatch')
    destination = SERVING_PACKAGE / relative
    if not destination.resolve().is_relative_to(SERVING_PACKAGE.resolve()) or destination.is_symlink():
        raise RuntimeError('Unsafe extraction destination')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != data:
        raise RuntimeError('Existing package changed; do not overwrite')
    destination.write_bytes(data)
del payloads
OHAYO_SERVING_ARM = ARM
os.environ.update(TOKENIZERS_PARALLELISM='false', USE_TF='0', USE_FLAX='0')
print('INPUT_VERIFIED:', ARM, '| no training dataset, no base weights in this ZIP')
'''

CELL_START = '''exec(compile((SERVING_PACKAGE / 'startup.py').read_text(encoding='utf-8'), 'ayo-serving-startup', 'exec'), globals())
print('SERVING_STARTED:', ARM, '| run the next cell to verify actual adapter state')
'''

CELL_VERIFY = '''import importlib.metadata, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from kaggle_secrets import UserSecretsClient

evidence = Path('/kaggle/working/ayo-serving-evidence-' + ARM)
evidence.mkdir(exist_ok=True)
report = dict(status='SERVING_VERIFICATION_FAILED',arm=ARM,
    package_sha256=EXPECTED_PACKAGE_SHA256,health=None,smoke=[],
    acceptance='Serving identity and synthetic gateway smoke only; not 36-case quality/security acceptance')
token = UserSecretsClient().get_secret('OHAYO_INFERENCE_TOKEN')
def local_request(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    request = Request('http://127.0.0.1:8765' + path, data=body,
        headers={'Authorization':'Bearer ' + token, 'Content-Type':'application/json'})
    try:
        with urlopen(request, timeout=110) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.loads(error.read(4096))

source = dict(source_id='S1',chunk_id='serving-smoke-1',
    document_id='11111111-1111-4111-8111-111111111111',
    version_id='22222222-2222-4222-8222-222222222222',
    document_title='Synthetic serving smoke',page_number=1,
    text='Chu kỳ lệnh gồm ba bước: nạp lệnh (Fetch), giải mã (Decode), thực thi (Execute).')
try:
    health_http, health = local_request('/health')
    report.update(health=health,health_http=health_http)
    assert health_http == 200 and health['ready'] and health['replicas'] == 2
    assert health['serving']['arm'] == ARM
    required = {'chat_history_v1','staged_hint_v1','diagnosed_hint_v1','summary_json_quotes_v1'}
    assert required <= set(health['capabilities'])
    assert len(health['serving']['replicas']) == 2
    for replica in health['serving']['replicas']:
        assert replica['adapter_sha256'] == (EXPECTED_ADAPTER_SHA256 if ARM == 'tuned_rag' else None)
        assert replica['tokenizer_source'] == 'verified_adapter_training_tokenizer'
        assert replica['tokenizer_json_sha256'] == manifest['files']['adapter/tokenizer/tokenizer.json']['sha256']
        if ARM == 'tuned_rag':
            assert replica['tensor_values_match'] and replica['loaded_adapter_tensors'] == 392
            assert replica['trainable_parameters'] == 0 and replica['active_adapter'] == 'default'
    report['dependencies'] = {name:importlib.metadata.version(name) for name in
        ['torch','transformers','tokenizers','bitsandbytes','accelerate','safetensors']}
    for attempt in range(2):
        started = time.monotonic()
        status, result = local_request('/generate', dict(question='Theo học liệu, chu kỳ lệnh gồm những bước nào?',
            mode='qa',contexts=[source],exercise=None,config=health['config'],history=[],history_protocol='chat_history_v1'))
        report['smoke'].append(dict(http=status,seconds=round(time.monotonic()-started,3),result=result))
    report['status'] = ('SERVING_SMOKE_PASSED' if all(row['http']==200
        and row['result'].get('output',{}).get('status')=='ANSWERED'
        and row['result']['output'].get('references')==[{'label':1,'source_id':'S1'}]
        for row in report['smoke']) else 'SERVING_SMOKE_FAILED')
except Exception as error:
    report['failure_type'] = type(error).__name__
(evidence/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(status=report['status'],arm=ARM,serving=(report.get('health') or {}).get('serving'),
    smoke_http=[row['http'] for row in report['smoke']]),indent=2))
print('Run cell 4 even if smoke failed. Do not change the backend URL yet.')
'''

CELL_EXPORT = '''from datetime import datetime, timezone
from IPython.display import FileLink, display
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
zip_path = Path('/kaggle/working/serving-' + ARM + '-' + stamp + '.zip')
with zipfile.ZipFile(zip_path,'x',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(evidence.glob('*.json')):
        archive.write(path,path.name)
receipt = dict(sha256=hashlib.sha256(zip_path.read_bytes()).hexdigest(),
    size_bytes=zip_path.stat().st_size,arm=ARM,package_sha256=EXPECTED_PACKAGE_SHA256)
receipt_path = zip_path.with_suffix('.receipt.json')
receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
display(FileLink(str(zip_path)),FileLink(str(receipt_path)))
print('Send ZIP + receipt and the cell 3 status. No training was performed.')
'''


def payloads():
    plan = json.loads((ROOT / PLAN).read_bytes())
    verify(ROOT / '.private/guardrails/baseline')
    identity = candidate_identity(plan)
    directory = ROOT / plan['candidate']['directory']
    training = ROOT / '.private/comparison/prepared/training-runner-v3/contents'
    binding = json.loads((directory.parent / 'package-binding.json').read_bytes())
    if hashlib.sha256((training / 'manifest.json').read_bytes()).hexdigest() != binding['package_manifest_sha256']:
        raise ValueError('Training tokenizer package is not bound to the selected run')
    training_manifest = json.loads((training / 'manifest.json').read_bytes())
    reference_bytes = (training / 'tokenizer-reference.json').read_bytes()
    if hashlib.sha256(reference_bytes).hexdigest() != training_manifest['files']['tokenizer-reference.json']['sha256']:
        raise ValueError('Training tokenizer reference changed')
    reference = json.loads(reference_bytes)
    tokenizer_bytes = (training / 'tokenizer/tokenizer.json').read_bytes()
    if hashlib.sha256(tokenizer_bytes).hexdigest() != reference['files']['tokenizer.json']['sha256']:
        raise ValueError('Training tokenizer changed')
    reference['serving_tokenizer_semantics_sha256'] = tokenizer_digest(json.loads(tokenizer_bytes))
    files = {f'adapter/{name}': (directory / name).read_bytes()
             for name in ('adapter_config.json', 'adapter_model.safetensors')}
    files['adapter/tokenizer-reference.json'] = json.dumps(reference,sort_keys=True,indent=2).encode()
    for name, expected in reference['files'].items():
        data = (training / 'tokenizer' / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected['sha256'] or len(data) != expected['size_bytes']:
            raise ValueError('Training tokenizer file changed: ' + name)
        files['adapter/tokenizer/' + name] = data
    records = {name.removeprefix('adapter/'): dict(sha256=hashlib.sha256(data).hexdigest(),size_bytes=len(data))
               for name,data in files.items()}
    files['adapter/serving-manifest.json'] = json.dumps(dict(schema_version=1,model=plan['model'],
        revision=plan['revision'],files=records),sort_keys=True,indent=2).encode()
    source = startup_source()
    marker = '_ohayo_service = _ohayo_dual_start()'
    if source.count(marker) != 1:
        raise ValueError('Startup entry point changed')
    source = source.replace(marker, (ROOT / 'scripts/kaggle_adapter_cell.py').read_text(encoding='utf-8'))
    compile(source, 'adapter-startup', 'exec')
    files['startup.py'] = source.encode()
    manifest = dict(schema_version=1,purpose='private_adapter_serving',adapter_sha256=identity['sha256'],
        files={name:dict(sha256=hashlib.sha256(data).hexdigest(),size_bytes=len(data)) for name,data in files.items()})
    files['manifest.json'] = json.dumps(manifest,sort_keys=True,indent=2).encode()
    return files, identity


def build(*, output=None, notebook_path=None):
    files, identity = payloads()
    output = Path(output) if output is not None else ROOT / '.private/guardrails/serving'
    output.mkdir(parents=True,exist_ok=True)
    archive_path = output / 'serving-input.zip'
    with ZipFile(archive_path,'w',ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info = ZipInfo(name, date_time=(1980,1,1,0,0,0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info,data)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    input_code = CELL_INPUT.replace('__PACKAGE_HASH__',repr(digest)).replace('__ADAPTER_HASH__',repr(identity['sha256']))
    input_code = input_code.replace('__MANIFEST_HASH__',repr(hashlib.sha256(files['manifest.json']).hexdigest()))
    cells = [dict(cell_type='markdown',id='guide',metadata={},source=[
        '# OHAYO - Adapter Serving\n\nPrivate inference trial, not training. Select GPU T4 x2 and Internet; attach the existing NF4 checkpoint and the new private serving Input. Enable NGROK_AUTHTOKEN and OHAYO_INFERENCE_TOKEN in Secrets.\n\nRun cells 1-4. Start in a fresh kernel. Keep the old Base notebook/version. For rollback restart Python, change ARM to base_rag in cell 1, then run cells 1-4 again. Never Run All in the old training notebook.\n'])]
    for name,code in [('input',input_code),('start',CELL_START),('verify',CELL_VERIFY),('export',CELL_EXPORT)]:
        compile(code,name,'exec')
        cells.append(dict(cell_type='code',id=name,metadata={},execution_count=None,outputs=[],source=code.splitlines(keepends=True)))
    notebook = dict(nbformat=4,nbformat_minor=5,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3')),cells=cells)
    path = Path(notebook_path) if notebook_path is not None else ROOT / 'notebooks/ayo_serving.ipynb'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    receipt = dict(package_sha256=digest,size_bytes=archive_path.stat().st_size,
        adapter_sha256=identity['sha256'],notebook_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        status='PREPARED_GPU_EXECUTION_PENDING',training_data_included=False,base_weights_included=False)
    (output / 'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,indent=2))
    return archive_path,path


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--notebook', type=Path)
    args = parser.parse_args()
    build(output=args.output, notebook_path=args.notebook)
