"""Authenticate returned smoke/main archives against the frozen generator package."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path, PurePosixPath
import shutil
from zipfile import ZipFile

from scripts.comparison.main_entry import smoke_gate
from scripts.comparison.protocol import read_rows, write_json
from scripts.comparison.runner import ARMS, audit_outputs, validate_config
from scripts.qlora.data import loads, read_json, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory

ROOT = Path(__file__).resolve().parents[2]
FILES = {'console.log', 'audit.json', 'measurements.jsonl', 'outputs.jsonl', 'progress.json',
         'run-plan.json', 'runtime.json', 'warmup.jsonl'}
PINS = dict(torch='2.11.0+cu130', transformers='4.57.6', peft='0.17.1',
            bitsandbytes='0.48.2', accelerate='1.10.1', safetensors='0.6.2')


def authenticate(archive, receipt_path, audit_path):
    receipt = read_json(receipt_path)
    require(receipt['archive'] == archive.name and receipt['sha256'] == sha_file(archive)
            and receipt['size_bytes'] == archive.stat().st_size, 'RETURNED_ARCHIVE_RECEIPT')
    require(receipt['process_exit_code'] == 0, 'RETURNED_PROCESS_FAILED')
    with ZipFile(archive) as zipped:
        names = zipped.namelist()
        require(len(names) == len(set(names)) and set(names) == FILES, 'RETURNED_ARCHIVE_FILES')
        require(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts
                    and '\\' not in n and ':' not in n for n in names), 'RETURNED_ARCHIVE_PATH')
        require(sum(i.file_size for i in zipped.infolist()) < 100 * 1024**2, 'RETURNED_ARCHIVE_SIZE')
        require(zipped.testzip() is None, 'RETURNED_ARCHIVE_CRC')
        payload = {name: zipped.read(name) for name in names}
    audit = loads(payload['audit.json'].decode('utf-8'))
    require(audit == receipt['audit'] == read_json(audit_path), 'RETURNED_AUDIT_COPIES')
    return payload, receipt


def finite(value):
    return type(value) in (float, int) and math.isfinite(value) and value >= 0


def validate_run(package, folder, mode):
    config = read_json(package / 'run-config.json')
    validate_config(config, mode)
    freeze = read_json(package / 'freeze.json')
    require(sha_file(package / 'freeze.json') == config['freeze_sha256'], 'INTAKE_FREEZE_PIN')
    for suffix, pin in freeze['input_files'].items():
        require(sha_file(package / 'inputs' / ('main.' + suffix)) == pin, 'INTAKE_MAIN_INPUT_PIN')
    plan = read_json(folder / 'run-plan.json')
    require(plan['mode'] == mode and plan['package_manifest_sha256'] == sha_file(package / 'manifest.json')
            and plan['config_sha256'] == sha_file(package / 'run-config.json'), 'RETURNED_RUN_BINDING')
    split = 'main' if mode == 'main' else 'dev'
    schedule = read_json(package / 'inputs' / (split + '.schedule.json'))
    if mode == 'smoke':
        schedule = schedule[:1]
    require(plan['schedule'] == schedule and plan['expected_rows'] == len(schedule) * 3,
            'RETURNED_RUN_SCHEDULE')
    models = {(r['qa_id'], r['arm']): r for r in
              read_rows(package / 'inputs' / (split + '.model-inputs.jsonl'))}
    keys = [(r['qa_id'], arm) for r in schedule for arm in r['arms']]
    outputs = read_rows(folder / 'outputs.jsonl')
    measurements = read_rows(folder / 'measurements.jsonl')
    require([(r['qa_id'], r['arm']) for r in outputs] == keys, 'RETURNED_OUTPUT_ORDER')
    require([(r['qa_id'], r['arm']) for r in measurements] == keys, 'RETURNED_MEASUREMENT_ORDER')
    audited = audit_outputs([models[k] for k in keys], outputs, config['adapter_sha256'])
    require(audited == read_json(folder / 'audit.json'), 'RETURNED_AUDIT_RECOMPUTED')
    require(all(r['run_id'] == plan['run_id'] for r in outputs), 'RETURNED_RUN_ID')
    assets = plan['assets']
    require(assets['adapter_sha256'] == config['adapter_sha256'] and assets['adapter_tensors'] == 392
            and assets['adapter_parameters'] == 20185088, 'RETURNED_ASSET_BINDING')
    runtime = read_json(folder / 'runtime.json')
    require(runtime['rows'] == len(keys) and runtime['run_id'] == plan['run_id'] and
            runtime['base_model_id'] == config['model_id'] and runtime['base_revision'] == config['model_revision']
            and runtime['packages'] == PINS and runtime['retry_count'] == 0, 'RETURNED_RUNTIME_BINDING')
    warmup = read_rows(folder / 'warmup.jsonl')
    require(len(warmup) == 6 and Counter(r['arm'] for r in warmup) == Counter({a: 2 for a in ARMS})
            and all(r['status'] == 'completed' for r in warmup), 'RETURNED_WARMUP')
    for row in measurements + warmup:
        enabled = row['arm'] == 'tuned_rag'
        require(row['adapter_state'] == dict(enabled=enabled, layers=196,
            disabled_layers=0 if enabled else 196, merged=False, active_adapter='selected'), 'RETURNED_LORA_STATE')
        require(all(finite(row[n]) for n in ('tokenization_seconds', 'peak_allocated_bytes', 'peak_reserved_bytes'))
                and (row['first_token_seconds'] is None or finite(row['first_token_seconds'])), 'RETURNED_TIMING')
    progress = read_json(folder / 'progress.json')
    require(progress['phase'] == 'FINISHED_IDENTITY_CHECKED' and progress['rows'] == len(keys)
            and progress['failure_rows'] == audited['failure_rows'], 'RETURNED_COMPLETION')
    arms = {}
    for arm in ARMS:
        rows = [r for r in outputs if r['arm'] == arm]
        times = sorted(r['generation_seconds'] for r in rows)
        arms[arm] = dict(rows=len(rows), status_counts=dict(Counter(r['status'] for r in rows)),
            mean_generation_seconds=sum(times) / len(times), generation_seconds_sum=sum(times),
            mean_output_tokens=sum(r['output_tokens'] for r in rows) / len(rows))
    return dict(status='RETURNED_RUN_INDEPENDENT_READBACK_PASSED', mode=mode, audit=audited,
        run_id=plan['run_id'], package_manifest_sha256=plan['package_manifest_sha256'],
        config_sha256=plan['config_sha256'], adapter_sha256=config['adapter_sha256'],
        arms=arms, generation_seconds_sum=sum(r['generation_seconds'] for r in outputs),
        peak_allocated_gib=max(r['peak_allocated_bytes'] for r in measurements) / 1024**3,
        peak_reserved_gib=max(r['peak_reserved_bytes'] for r in measurements) / 1024**3,
        noncompleted=[{k: r[k] for k in ('qa_id','arm','status','stop_reason','output_tokens')}
                      for r in outputs if r['status'] != 'completed'], factuality='NOT_EVALUATED')


def receive(downloads, output):
    state_path = ROOT / '.private/comparison/experiment-readiness.json'
    state = read_json(state_path)
    package = (ROOT / state['main_package_path']).parent / 'contents'
    verify_inventory(package, read_json(package / 'manifest.json')['files'])
    require(not output.exists() and output.resolve().is_relative_to(ROOT / '.private'), 'NEW_PRIVATE_INTAKE')
    specs = [('smoke', 'smoke-20261113T010750639983Z', 'audit (2).json'),
             ('main', 'main-20261113T011502419787Z', 'audit (3).json')]
    incoming = {mode: authenticate(downloads / (name + '.zip'), downloads / (name + '-receipt.json'),
                                   downloads / audit) for mode, name, audit in specs}
    output.mkdir(parents=True)
    reports = {}
    for mode, name, audit in specs:
        folder = output / name
        folder.mkdir()
        for filename, raw in incoming[mode][0].items():
            (folder / filename).write_bytes(raw)
        for filename in (name + '.zip', name + '-receipt.json'):
            shutil.copyfile(downloads / filename, output / filename)
        shutil.copyfile(downloads / audit, output / (name + '-audit.json'))
        reports[mode] = validate_run(package, folder, mode)
        reports[mode]['archive_sha256'] = incoming[mode][1]['sha256']
    smoke_gate(package, output / specs[0][1])
    write_json(output / 'readback.json', reports)
    write_json(output / 'manifest.json', dict(files=inventory(output)))
    state.update(status='STEP7_MAIN_RECEIVED_900_ROWS_PENDING_SEMANTIC_SCORING', main_completed=True,
        main_authorized=True, main_intake_path=output.relative_to(ROOT).as_posix(),
        main_readback_sha256=sha_file(output / 'readback.json'),
        main_status_counts=reports['main']['audit']['status_counts'], main_semantic_scoring='NOT_RUN',
        adapter_runtime_reload='SELECTED_ADAPTER_196_LORA_LAYERS_VERIFIED_SMOKE_AND_MAIN')
    write_json(state_path, state)
    return reports


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--downloads', type=Path, default=Path('D:/Downloads'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(receive(args.downloads, args.output.resolve()), indent=2))
