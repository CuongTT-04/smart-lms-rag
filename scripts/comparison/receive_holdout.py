"""Authenticate received holdout evidence and recompute its audit without GPU."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import shutil
import stat
from zipfile import ZipFile

from scripts.comparison.holdout import ADAPTER_SHA, ARMS, audit
from scripts.comparison.protocol import read_rows, write_json
from scripts.qlora.data import read_json, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory

MEMBERS = {'console.log', 'artifacts.json', 'audit.json', 'outputs.jsonl', 'plan.json',
           'progress.json', 'runtime.json', 'figures/loss.png', 'figures/format.png'}


def authenticate(archive, receipt, separate_audit):
    receipt = read_json(receipt)
    require(sha_file(archive) == receipt['sha256'] and archive.stat().st_size == receipt['size_bytes']
            and archive.name == receipt['archive'] and receipt['process_exit_code'] == 0, 'HOLDOUT_RECEIPT')
    with ZipFile(archive) as zipped:
        infos = zipped.infolist()
        require(len(infos) == len(MEMBERS) and {i.filename for i in infos} == MEMBERS, 'HOLDOUT_ARCHIVE_MEMBERS')
        require(all(not i.is_dir() and not stat.S_ISLNK(i.external_attr >> 16) and not i.flag_bits & 1 for i in infos)
                and sum(i.file_size for i in infos) <= 32 * 1024 * 1024, 'HOLDOUT_ARCHIVE_TYPE_OR_SIZE')
        files = {i.filename: zipped.read(i) for i in infos}
    reported = json.loads(files['audit.json'])
    require(reported == receipt['audit'] == read_json(separate_audit), 'HOLDOUT_AUDIT_COPIES')
    manifest = json.loads(files['artifacts.json'])
    require(set(manifest) == MEMBERS - {'console.log', 'artifacts.json'}, 'HOLDOUT_ARTIFACT_MANIFEST')
    for name, entry in manifest.items():
        require(len(files[name]) == entry['size_bytes']
                and hashlib.sha256(files[name]).hexdigest() == entry['sha256'], 'HOLDOUT_ARTIFACT_HASH:' + name)
    return files, receipt


def receive(archive, receipt, separate_audit, package, output):
    files, transport = authenticate(archive, receipt, separate_audit)
    output, package = output.resolve(), package.resolve()
    require(not output.exists() and not output.is_relative_to(package)
            and not package.is_relative_to(output), 'NEW_DISJOINT_HOLDOUT_INTAKE')
    output.mkdir(parents=True)
    run = output / 'run'
    for name, raw in files.items():
        path = run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    plan, runtime = read_json(run / 'plan.json'), read_json(run / 'runtime.json')
    config = read_json(package / 'run-config.json')
    inputs = read_rows(package / 'data/holdout.jsonl')
    require(plan['split'] == 'holdout' and plan['record_ids'] == [r['record_id'] for r in inputs]
            and plan['package_manifest_sha256'] == sha_file(package / 'manifest.json')
            and plan['generation'] == config['generation'] and plan['optimizer_steps'] == 0
            and plan['reference_not_in_generation_prompt'] is True, 'HOLDOUT_PLAN_BINDING')
    require(runtime['assets']['adapter_sha256'] == ADAPTER_SHA
            and runtime['assets']['model_id'] == config['model_id']
            and runtime['assets']['revision'] == config['model_revision'], 'HOLDOUT_RUNTIME_IDENTITY')
    expected_versions = dict(transformers='4.57.6', peft='0.17.1', bitsandbytes='0.48.2',
                             accelerate='1.10.1', safetensors='0.6.2')
    require(all(runtime['packages'][name] == expected for name, expected in expected_versions.items())
            and '+cu' in runtime['packages']['torch'], 'HOLDOUT_RUNTIME_PACKAGES')
    rows = read_rows(run / 'outputs.jsonl')
    order = [(r['record_id'], arm) for i, r in enumerate(inputs)
             for arm in (ARMS if i % 2 == 0 else tuple(reversed(ARMS)))]
    require([(r['record_id'], r['arm']) for r in rows] == order, 'HOLDOUT_GENERATION_ORDER')
    for row in rows:
        require(type(row['output_tokens']) is int and 0 <= row['output_tokens'] <= 512
                and math.isfinite(row['generation_seconds']) and row['generation_seconds'] >= 0
                and row['measurements']['adapter_state']['active_adapter'] == 'selected'
                and row['measurements']['peak_allocated_bytes'] > 0, 'HOLDOUT_MEASUREMENTS')
        if row['status'] == 'completed':
            require(row['stop_reason'] == 'eos' and row['error'] is None, 'HOLDOUT_STOP_REASON')
    recomputed = audit(package, run, 'holdout')
    require(recomputed == read_json(run / 'audit.json'), 'HOLDOUT_INDEPENDENT_RECOMPUTATION')
    require(read_json(run / 'progress.json') == dict(phase='FINISHED', rows=232, expected_rows=232), 'HOLDOUT_FINISH_MARKER')
    lookup = {(r['record_id'], r['arm']): r for r in rows}
    paired = Counter()
    for item in inputs:
        base, tuned = [lookup[item['record_id'], arm] for arm in ARMS]
        paired['tuned_lower_nll' if tuned['nll_sum'] < base['nll_sum'] else
               'base_lower_nll' if base['nll_sum'] < tuned['nll_sum'] else 'equal_nll'] += 1
        paired['exact_gain' if tuned['scores']['reference_exact'] and not base['scores']['reference_exact'] else
               'exact_loss' if base['scores']['reference_exact'] and not tuned['scores']['reference_exact'] else 'exact_tie'] += 1
    report = dict(status='HOLDOUT_RECEIVED_AND_INDEPENDENTLY_RECOMPUTED',
                  archive_sha256=transport['sha256'], audit=recomputed, paired=dict(paired),
                  evidence_scope='CPU recheck of submitted GPU records; no independent GPU rerun or semantic correctness claim',
                  runtime_asset_flags='assets.base_weights_loaded=false/runtime_reload=PENDING_GPU_SMOKE are inherited pre-load asset-check metadata, not post-load execution status.')
    shutil.copyfile(archive, output / archive.name)
    shutil.copyfile(receipt, output / 'receipt.json')
    shutil.copyfile(separate_audit, output / 'submitted-audit.json')
    write_json(output / 'verification.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'receipt', 'audit', 'package', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    receive(args.archive, args.receipt, args.audit, args.package, args.output)
