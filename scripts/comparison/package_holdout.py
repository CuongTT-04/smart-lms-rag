"""Package a frozen 116-record instruction holdout; never export train data."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import shutil

from scripts.comparison.holdout import ADAPTER_SHA, DATA_SHA, TASKS
from scripts.comparison.instruction_source import archive_files
from scripts.comparison.package_runner import make_notebook
from scripts.comparison.protocol import digest, read_rows, write_bundle, write_json, write_rows
from scripts.qlora.data import read_json, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory

ROOT = Path(__file__).resolve().parents[2]


def select_rows(source, split):
    payloads = read_rows(source / (split + '.jsonl'))
    metadata = read_rows(source / (split + '.metadata.jsonl'))
    tokens = read_rows(source / ('tokenized-' + split + '.jsonl'))
    require(len(payloads) == len(metadata) == len(tokens), 'HOLDOUT_SIDECAR_COUNT')
    rows = []
    for index, (payload, meta, token) in enumerate(zip(payloads, metadata, tokens)):
        require(meta['row_index'] == index and meta['split'] == split
                and meta['record_id'] == token['record_id']
                and meta['training_payload_sha256'] == digest(payload), 'HOLDOUT_SOURCE_BINDING')
        rows.append(dict(record_id=meta['record_id'], task_type=meta['task_type'],
                         course_code=meta['course_code'], payload_sha256=digest(payload), payload=payload))
    return rows, metadata, tokens


def make_evaluation_notebook(archive, receipt):
    doc = make_notebook(None, archive, receipt['zip_sha256'])
    bootstrap = ''.join(doc['cells'][1]['source']).replace('runner-dev.zip', archive.name)
    bootstrap = bootstrap.replace('comparison-package-', 'holdout-package-').replace('comparison-env/bin/python', 'holdout-env/bin/python')
    bootstrap = bootstrap.replace('Package authenticated. Main locked. Qwen weights not loaded.', 'Holdout package authenticated. No training. Qwen not loaded yet.')
    setup = '''ENV = Path('/kaggle/working/holdout-env')
subprocess.run([sys.executable, '-m', 'venv', '--without-pip', '--system-site-packages', str(ENV)], check=True)
from importlib.metadata import version
torch_before = version('torch')
constraint = ENV / 'torch-constraint.txt'
constraint.write_text('torch==' + torch_before + '\\n')
subprocess.run([sys.executable, '-m', 'pip', '--python', str(PYTHON), 'install', '--disable-pip-version-check', '--constraint', str(constraint), '-r', str(PACKAGE / 'scripts/comparison/requirements.txt')], check=True)
torch_after = subprocess.run([str(PYTHON), '-c', 'from importlib.metadata import version; print(version("torch"))'], check=True, capture_output=True, text=True).stdout.strip()
assert torch_before == torch_after, 'CUDA torch changed'
subprocess.run([str(PYTHON), '-B', '-m', 'scripts.comparison.holdout', '--package', str(PACKAGE), '--check-only'], cwd=PACKAGE, check=True)
print('Environment and 116 holdout token/mask checks passed. GPU evaluation not run yet.')
'''
    execute = ''.join(doc['cells'][3]['source'])
    execute = execute.replace('scripts.comparison.runner', 'scripts.comparison.holdout').replace("'--mode', mode", "'--split', mode")
    execute = execute.replace('/kaggle/working/comparison-runs', '/kaggle/working/holdout-runs')
    execute = execute.replace('SMOKE_RUN, SMOKE_AUDIT', 'SMOKE_RUN, SMOKE_AUDIT')
    full = '''assert SMOKE_AUDIT['rows'] == 8 and SMOKE_AUDIT['failed_generations'] == 0, 'Resolve validation smoke failures before opening holdout.'
HOLDOUT_RUN, HOLDOUT_AUDIT = execute('holdout')
assert HOLDOUT_AUDIT['rows'] == 232
print('Figures:', HOLDOUT_RUN / 'figures')
print('Send holdout ZIP, receipt and audit.json. Do not select or retrain an adapter using these scores.')
'''
    for cell, text in zip(doc['cells'][1:], (bootstrap, setup, execute, full)):
        cell['source'] = text.splitlines(keepends=True)
    doc['cells'][0]['source'] = ['# Instruction holdout evaluation\n',
        'One T4 + Internet. Separate from the chatbot serving session. Add the exact holdout-evaluation ZIP dataset; no checkpoint Input or secrets needed. Base weights may download once. Run cells in order: authenticate, environment, validation smoke, 116 holdout. No training.\n']
    return doc


def build(output):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT / '.private') and not output.exists(), 'NEW_PRIVATE_HOLDOUT_PACKAGE_REQUIRED')
    state = read_json(ROOT / '.private/comparison/experiment-readiness.json')
    require(state['selected_adapter_sha256'] == ADAPTER_SHA and state['expanded_adapter_selected'] is True, 'HOLDOUT_PRESELECTED_ADAPTER')
    source = ROOT / Path(state['training_path'].replace('\\', '/'))
    require(sha_file(source / 'manifest.json') == DATA_SHA, 'HOLDOUT_DATA_MANIFEST_PIN')
    manifest = read_json(source / 'manifest.json')
    verify_inventory(source, manifest['files'])
    archive_files(ROOT / '.private/comparison/inputs/instruction/package.zip')
    require(manifest['split_counts'] == dict(train=770, validation=114, instruction_holdout=116), 'HOLDOUT_SPLIT_COUNTS')
    records, metadata, tokens = select_rows(source, 'instruction_holdout')
    require(len(records) == 116 and dict(Counter(r['task_type'] for r in records)) == TASKS, 'HOLDOUT_LOCKED_COUNTS')
    ids = {r['record_id'] for r in records}
    groups = {g for r in metadata for g in r['source_group_ids']}
    families = {r['variant_family_id'] for r in metadata}
    for split in ('train', 'validation'):
        other = read_rows(source / (split + '.metadata.jsonl'))
        require(not ids & {r['record_id'] for r in other}
                and not groups & {g for r in other for g in r['source_group_ids']}
                and not families & {r['variant_family_id'] for r in other}, 'HOLDOUT_SPLIT_LEAKAGE')
    validation, _, validation_tokens = select_rows(source, 'validation')
    indices = [next(i for i, row in enumerate(validation) if row['task_type'] == task) for task in sorted(TASKS)]
    contents = output / 'contents'
    contents.mkdir(parents=True)
    write_rows(contents / 'data/holdout.jsonl', records)
    write_rows(contents / 'data/tokenized-holdout.jsonl', tokens)
    write_rows(contents / 'data/smoke.jsonl', [validation[i] for i in indices])
    write_rows(contents / 'data/tokenized-smoke.jsonl', [validation_tokens[i] for i in indices])
    assets = ROOT / '.private/comparison/prepared/main-runner-fixed/contents'
    asset_manifest = read_json(assets / 'manifest.json')
    asset_names = ['adapter/adapter_config.json', 'adapter/adapter_model.safetensors', 'tokenizer-reference.json']
    asset_names += ['tokenizer/' + name for name in read_json(assets / 'tokenizer-reference.json')['files']]
    verify_inventory(assets, {name: asset_manifest['files'][name] for name in asset_names})
    files = ['scripts/comparison/__init__.py', 'scripts/qlora/__init__.py',
             *('scripts/comparison/' + name for name in ('holdout.py', 'runner.py', 'packing.py', 'protocol.py', 'requirements.txt')),
             *('scripts/qlora/' + name for name in ('data.py', 'runtime.py', 'requirements.txt'))]
    for name in files + asset_names:
        target = contents / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile((assets if name in asset_names else ROOT) / name, target)
    (contents / 'scripts/comparison/requirements.txt').write_text(
        (ROOT / 'scripts/comparison/requirements.txt').read_text(encoding='utf-8') + '\nmatplotlib>=3.8,<4\n', encoding='utf-8')
    config = deepcopy(read_json(assets / 'run-config.json'))
    config.update(protocol='instruction-holdout-v1', training=False, stage='HOLDOUT_FROZEN',
                  main_authorized=False, token_limits=read_json(source / 'dataset-config.json')['token_limits'],
                  holdout_counts=TASKS, selection='ALREADY_SELECTED_BEFORE_HOLDOUT',
                  source_overlap='Instruction holdout sources were also used by the earlier main benchmark; not a new unseen-source test.')
    # Keep only runtime identity and the explicit holdout policy, not main/dev scores.
    keep = ('model_id', 'model_revision', 'adapter_sha256', 'adapter_config_sha256', 'generation',
            'attempts', 'training_manifest_sha256', 'protocol', 'training', 'stage', 'main_authorized',
            'token_limits', 'holdout_counts', 'selection', 'source_overlap')
    config = {key: config[key] for key in keep}
    write_json(contents / 'run-config.json', config)
    write_json(contents / 'manifest.json', dict(files=inventory(contents)))
    receipt = write_bundle(contents, output / 'holdout-evaluation.zip')
    notebook = make_evaluation_notebook(output / 'holdout-evaluation.zip', receipt)
    notebook_path = ROOT / 'notebooks/instruction_holdout.ipynb'
    require(not notebook_path.exists(), 'HOLDOUT_NOTEBOOK_ALREADY_EXISTS')
    write_json(notebook_path, notebook)
    report = dict(status='HOLDOUT_PACKAGE_BUILT_GPU_NOT_RUN', records=116, expected_output_rows=232,
                  validation_smoke_cases=4, task_counts=TASKS, adapter_sha256=ADAPTER_SHA,
                  training_manifest_sha256=DATA_SHA, split_id_group_family_checks='PASSED',
                  archive=receipt, dataset_public=False, training=False, tokenizer_recheck='PENDING_OFFLINE_PREFLIGHT',
                  next_action='Import instruction_holdout.ipynb and add the generated private Input ZIP on Kaggle.')
    write_json(output / 'preflight.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
