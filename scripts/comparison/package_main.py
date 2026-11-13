"""Export the frozen main experiment, never train or include evaluator answers."""
import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys

from scripts.comparison.freeze import ROOT, verify_locked
from scripts.comparison.package_runner import copy, make_notebook
from scripts.comparison.protocol import read_rows, write_bundle, write_json
from scripts.comparison.runner import audit_assets, validate_config, validate_inputs
from scripts.qlora.data import read_json, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory


RUNTIME_FILES = {
    'scripts/comparison/' + name for name in
    ('__init__.py', 'runner.py', 'packing.py', 'protocol.py', 'requirements.txt')
} | {
    'scripts/qlora/' + name for name in ('__init__.py', 'data.py', 'runtime.py', 'requirements.txt')
}
ENTRY_FILES = {'scripts/comparison/kaggle.py', 'scripts/comparison/main_entry.py'}


def copy_runtime(source, contents):
    assets = {name for name in inventory(source) if name.startswith(('adapter/', 'tokenizer/', 'data/comparison/'))}
    assets.add('tokenizer-reference.json')
    for name in sorted(assets | RUNTIME_FILES):
        copy(source / name, contents / name)
    for name in sorted(ENTRY_FILES):
        copy(ROOT / name, contents / name)
    return assets | RUNTIME_FILES | ENTRY_FILES


def probe_entrypoints(contents):
    reports = {}
    environment = os.environ.copy()
    # Probe only the exported package, without borrowing modules from the checkout.
    environment.pop('PYTHONPATH', None)
    for module in ('kaggle', 'runner', 'main_entry'):
        name = 'scripts.comparison.' + module
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-m', name, '--help'],
                                cwd=contents, env=environment, capture_output=True, text=True, encoding='utf-8', errors='replace')
        require(result.returncode == 0 and '--package' in result.stdout,
                'MAIN_PACKAGE_ENTRYPOINT:' + name + ':' + result.stderr[-2000:])
        reports[name] = 'HELP_ENTRYPOINT_PASSED_NO_MODEL_CALL'
    return reports


def main_notebook(archive, pin):
    notebook = make_notebook(None, archive, pin)
    notebook['cells'][0]['source'] = ['# OHAYO - Main Evaluation\n',
        'T4, Internet; inference only. Run the four code cells in order.\n']
    cells = [c for c in notebook['cells'] if c['cell_type'] == 'code']
    bootstrap = ''.join(cells[0]['source']).replace('runner-dev.zip', 'runner-main.zip')
    bootstrap = bootstrap.replace('comparison-package-', 'comparison-main-package-')
    bootstrap = bootstrap.replace('Package authenticated. Main locked. Qwen weights not loaded.',
        'Frozen package authenticated. Smoke required before main. Qwen weights not loaded.')
    cells[0]['source'] = bootstrap.splitlines(keepends=True)
    cells[1]['source'] = ''.join(cells[1]['source']).replace('Smoke/dev', 'Smoke/main').splitlines(keepends=True)
    common = ''.join(cells[2]['source']).replace('comparison-runs', 'comparison-main-runs')
    old = "        process = subprocess.Popen([str(PYTHON), '-B', '-m', 'scripts.comparison.runner', '--package', str(PACKAGE), '--output', str(run), '--mode', mode], cwd=PACKAGE, stdout=log, stderr=subprocess.STDOUT)"
    require(old in common, 'MAIN_NOTEBOOK_SOURCE_PATTERN')
    new = """        command = [str(PYTHON), '-B', '-m', 'scripts.comparison.runner', '--package', str(PACKAGE), '--output', str(run), '--mode', mode]
        if mode == 'main':
            command = [str(PYTHON), '-B', '-m', 'scripts.comparison.main_entry', '--package', str(PACKAGE), '--output', str(run), '--smoke-run', str(SMOKE_RUN)]
        process = subprocess.Popen(command, cwd=PACKAGE, stdout=log, stderr=subprocess.STDOUT)"""
    common = common.replace(old, new)
    common = common.replace("    assert process.returncode == 0 and audit is not None,",
        "    if process.returncode != 0: print(console.read_text(encoding='utf-8')[-12000:])\n"
        "    assert process.returncode == 0 and audit is not None,")
    cells[2]['source'] = common.splitlines(keepends=True)
    cells[3]['source'] = """assert SMOKE_AUDIT['rows'] == 3 and SMOKE_AUDIT['failure_rows'] == 0, 'Resolve smoke failures before main.'
MAIN_RUN, MAIN_AUDIT = execute('main')
assert MAIN_AUDIT['rows'] == 900, 'Keep the failure ZIP; do not silently retry.'
print('Main generation exported. Semantic scoring has NOT run. Preserve raw failures in the denominator.')
""".splitlines(keepends=True)
    for cell in cells:
        ast.parse(''.join(cell['source']))
    return notebook


def build(output):
    output = output.resolve()
    require(output.is_relative_to(ROOT / '.private') and not output.exists(), 'NEW_PRIVATE_MAIN_PACKAGE')
    state_path = ROOT / '.private/comparison/experiment-readiness.json'
    state = read_json(state_path)
    frozen = ROOT / state['freeze_path']
    verify_inventory(frozen, read_json(frozen / 'manifest.json')['files'])
    verify_locked(ROOT, read_json(frozen / 'source-lock.json')['files'])
    config = read_json(frozen / 'run-config.json')
    freeze = read_json(frozen / 'freeze.json')
    require(sha_file(frozen / 'freeze.json') == config['freeze_sha256'] == state['freeze_sha256'],
            'MAIN_FROZEN_CONFIG_BINDING')
    validate_config(config, 'main')
    source = ROOT / '.private/comparison/runs/full-20261112T192034516377Z-dev-package-linux'
    retrieval = ROOT / state['retrieval_path']
    contents = output / 'contents'
    runtime_files = copy_runtime(source, contents)
    for name in ('freeze.json', 'run-config.json'):
        copy(frozen / name, contents / name)
    for split, bindings in (('dev', freeze['dev_input_files']), ('main', freeze['input_files'])):
        for suffix, pin in bindings.items():
            path = retrieval / (split + '.' + suffix)
            require(sha_file(path) == pin, 'MAIN_INPUT_PIN')
            copy(path, contents / 'inputs' / path.name)
    tokenizer, assets = audit_assets(contents, config)
    for split in ('dev', 'main'):
        validate_inputs(*[read_rows(contents / 'inputs' / (split + '.' + n + '.jsonl'))
                          for n in ('inputs','cache','model-inputs')], tokenizer)
    files = inventory(contents)
    allowed = runtime_files | {'freeze.json', 'run-config.json'}
    allowed |= {'inputs/dev.' + n for n in freeze['dev_input_files']}
    allowed |= {'inputs/main.' + n for n in freeze['input_files']}
    require(set(files) == allowed, 'MAIN_EXPORT_ALLOWLIST')
    write_json(contents / 'manifest.json', dict(files=files))
    entrypoints = probe_entrypoints(contents)
    archive = output / 'runner-main.zip'
    receipt = write_bundle(contents, archive)
    notebook = main_notebook(archive, receipt['zip_sha256'])
    write_json(ROOT / 'notebooks/comparison_main.ipynb', notebook)
    write_json(output / 'preflight.json', dict(status='MAIN_PACKAGE_READY_GPU_EXECUTION_NOT_RUN',
        main_cases=300, main_outputs=900, smoke_outputs=3, assets=assets,
        gold_packaged=False, training_packaged=False, fresh_smoke_required=True,
        freeze_sha256=config['freeze_sha256'], zip_sha256=receipt['zip_sha256'],
        entrypoints=entrypoints))
    state.update(status='STEP7_PACKAGE_READY_AWAITING_KAGGLE_SMOKE_AND_MAIN',
        main_package_path=archive.relative_to(ROOT).as_posix(), main_package_sha256=receipt['zip_sha256'],
        main_notebook='notebooks/comparison_main.ipynb', main_authorized=False, main_completed=False)
    write_json(state_path, state)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(build(parser.parse_args().output))
