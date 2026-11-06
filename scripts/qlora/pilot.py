"""Audit and export the fresh 50-step pilot, without loading Qwen or pickle state."""
import argparse
import math
from pathlib import Path
import shutil
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from .data import digest, read_json, read_rows, require, sha_file
from .runtime import validate_recipe, write_json
from .smoke import audit_training


def audit(run):
    run = Path(run).resolve()
    report = audit_training(run, profile='pilot', steps=50)
    config = read_json(run / 'resolved-config.json')
    validate_recipe(config, 'pilot')
    recipe = Path(__file__).resolve().parents[2] / 'configs/qlora-pilot.json'
    require(digest(config) == digest(read_json(recipe)), 'PILOT_RECIPE_IDENTITY')
    reference = read_json(run / 'data-reference.json')
    require(reference.get('resume_checkpoint') is None
            and reference.get('resume_manifest_sha256') is None, 'PILOT_MUST_START_FRESH')
    args = read_json(run / 'training-arguments.json')
    require(args['save_steps'] == args['eval_steps'] == 25
            and args['save_total_limit'] == 2, 'PILOT_CHECKPOINT_SCHEDULE')
    require(all(args.get(key) == value for key, value in config['training'].items())
            and args.get('seed') == args.get('data_seed') == config['seed']
            and args.get('gradient_checkpointing') is True, 'PILOT_TRAINING_RECIPE')
    evaluations = {r['step']: r['eval_loss'] for r in read_rows(run / 'train-metrics.jsonl')
                   if 'eval_loss' in r}
    require(set(evaluations) == {25, 50}
            and all(math.isfinite(v) for v in evaluations.values()), 'PILOT_EVALUATION_STEPS')
    require(evaluations[50] == report['eval_loss'], 'PILOT_FINAL_EVAL_MISMATCH')
    expected = {'checkpoint-25', 'checkpoint-50'}
    require({p.name for p in run.glob('checkpoint-*')} == expected, 'PILOT_CHECKPOINT_SET')
    required = {'adapter_config.json', 'adapter_model.safetensors', 'trainer_state.json',
                'optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'scaler.pt', 'binding.json'}
    from safetensors import safe_open
    import torch
    for step in (25, 50):
        folder = run / ('checkpoint-' + str(step))
        require(required <= {p.name for p in folder.iterdir()}, 'PILOT_CHECKPOINT_INCOMPLETE')
        require(read_json(folder / 'trainer_state.json')['global_step'] == step, 'PILOT_CHECKPOINT_STEP')
        binding = read_json(folder / 'binding.json')
        require(binding['config_sha256'] == digest(config)
                and binding['data_manifest_sha256'] == config['data_manifest_sha256']
                and binding['global_step'] == step, 'PILOT_CHECKPOINT_BINDING')
        with safe_open(folder / 'adapter_model.safetensors', framework='pt', device='cpu') as tensors:
            require(bool(tensors.keys()) and all('lora_' in key
                    and torch.isfinite(tensors.get_tensor(key)).all().item() for key in tensors.keys()),
                    'PILOT_CHECKPOINT_TENSORS')
        adapter = read_json(folder / 'adapter_config.json')
        require(adapter['base_model_name_or_path'] == config['model_id']
                and adapter['revision'] == config['revision']
                and all(adapter[key] == config['lora'][key]
                        for key in ('r', 'lora_alpha', 'lora_dropout', 'bias', 'task_type')),
                'PILOT_ADAPTER_IDENTITY')
    report.update(checkpoints=sorted(expected), eval_loss_by_step=evaluations,
                  initialization='PINNED_BASE_WITH_FRESH_LORA', gpu_reload='NOT_RUN',
                  gpu_resume='NOT_RUN', quality_improvement='NOT_ESTABLISHED')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args(argv)
    run = args.run.resolve()
    report = audit(run)
    report_path = run.with_name(run.name + '-audit.json')
    if report_path.exists():
        require(read_json(report_path) == read_json_value(report), 'PILOT_AUDIT_OUTPUT_DIFFERS')
    else:
        write_json(report_path, report)
    archive = run.with_name(run.name + '.zip')
    receipt = run.with_name(run.name + '-receipt.json')
    require(not archive.exists() and not receipt.exists(), 'PILOT_EXPORT_EXISTS')
    needed = sum(p.stat().st_size for p in run.rglob('*') if p.is_file())
    require(shutil.disk_usage(run.parent).free >= needed + 256 * 1024 ** 2,
            'INSUFFICIENT_SPACE_FOR_PILOT_ZIP')
    with ZipFile(archive, 'x', compression=ZIP_DEFLATED) as zipped:
        for path in sorted(run.rglob('*')):
            if path.is_file():
                zipped.write(path, path.relative_to(run).as_posix())
    write_json(receipt, dict(file=archive.name, sha256=sha_file(archive),
        size_bytes=archive.stat().st_size, audit_file=report_path.name,
        audit_sha256=sha_file(report_path), run_manifest_sha256=report['run_manifest_sha256'],
        model_revision=read_json(run / 'resolved-config.json')['revision'], global_step=50,
        scope='PRIVATE_GPU_PILOT_HANDOFF', base_weights_included=False))
    print('GPU_PILOT_PASSED: ' + str(report_path))
    print('Private artifact: ' + str(archive))
    return 0


def read_json_value(value):
    # Normalize integer step keys to the representation stored in JSON reports.
    import json
    return json.loads(json.dumps(value, allow_nan=False))


if __name__ == '__main__':
    sys.exit(main())
