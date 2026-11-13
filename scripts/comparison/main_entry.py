"""Main inference entry point: require a successful smoke of this exact package."""
import argparse
from pathlib import Path

from scripts.comparison.protocol import read_rows
from scripts.comparison.runner import ARMS, audit_outputs, run
from scripts.qlora.data import read_json, require, sha_file


def smoke_gate(package, smoke):
    package, smoke = Path(package), Path(smoke)
    config = read_json(package / 'run-config.json')
    plan = read_json(smoke / 'run-plan.json')
    require(plan['mode'] == 'smoke' and plan['expected_rows'] == 3, 'MAIN_REQUIRES_SMOKE')
    require(plan['package_manifest_sha256'] == sha_file(package / 'manifest.json') and
            plan['config_sha256'] == sha_file(package / 'run-config.json'), 'MAIN_SMOKE_PACKAGE_BINDING')
    schedule = read_json(package / 'inputs/dev.schedule.json')[:1]
    require(plan['schedule'] == schedule, 'MAIN_SMOKE_SCHEDULE')
    models = read_rows(package / 'inputs/dev.model-inputs.jsonl')
    expected = [r for r in models if r['qa_id'] == schedule[0]['qa_id']]
    report = audit_outputs(expected, read_rows(smoke / 'outputs.jsonl'), config['adapter_sha256'])
    require(report['rows'] == 3 and report['failure_rows'] == 0, 'MAIN_SMOKE_FAILED')
    require(read_json(smoke / 'audit.json') == report, 'MAIN_SMOKE_AUDIT_CHANGED')
    runtime = read_json(smoke / 'runtime.json')
    require(runtime['rows'] == 3 and runtime['base_revision'] == config['model_revision'] and
            runtime['base_model_id'] == config['model_id'], 'MAIN_SMOKE_RUNTIME')
    warmup = read_rows(smoke / 'warmup.jsonl')
    require(len(warmup) == 6 and all(r['status'] == 'completed' for r in warmup) and
            all(sum(r['arm'] == a for r in warmup) == 2 for a in ARMS), 'MAIN_SMOKE_WARMUP')
    measurements = read_rows(smoke / 'measurements.jsonl')
    require(len(measurements) == 3 and {r['arm'] for r in measurements} == set(ARMS) and
            all(r['qa_id'] == schedule[0]['qa_id'] for r in measurements), 'MAIN_SMOKE_MEASUREMENTS')
    for row in warmup + measurements:
        enabled = row['arm'] == 'tuned_rag'
        state = row['adapter_state']
        require(state == dict(enabled=enabled, layers=196, disabled_layers=0 if enabled else 196,
                              merged=False, active_adapter='selected'), 'MAIN_SMOKE_LORA_STATE')
    return report


def no_previous_main(package, parent):
    pin = sha_file(Path(package) / 'manifest.json')
    for path in Path(parent).glob('*/run-plan.json'):
        plan = read_json(path)
        require(not (plan.get('mode') == 'main' and plan.get('package_manifest_sha256') == pin),
                'MAIN_ALREADY_STARTED_KEEP_RAW_DO_NOT_RETRY')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--smoke-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    smoke_gate(args.package, args.smoke_run)
    no_previous_main(args.package, args.output.parent)
    run(args.package, args.output, 'main')
