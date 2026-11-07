"""Audit and package a completed two-step GPU smoke, without loading Qwen again."""
import argparse
import math
from pathlib import Path
import shutil
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from .data import digest, read_json, read_rows, require, sha_file
from .runtime import inventory, verify_inventory, write_json


def audit(run):
    return audit_training(run, profile='smoke', steps=2)


def audit_training(run, *, profile, steps):
    run = Path(run).resolve()
    manifest = read_json(run / 'run-manifest.json')
    require(manifest['status'] == 'TRAINING_COMPLETED' and manifest['profile'] == profile,
            'NOT_COMPLETED_GPU_SMOKE')
    verify_inventory(run, manifest['files'])
    require(set(inventory(run, ('run-manifest.json', 'SHA256SUMS.txt'))) == set(manifest['files']),
            'SMOKE_UNLISTED_FILES')
    sums = {}
    for line in (run / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        sha, name = line.split('  ', 1)
        require(name not in sums, 'SMOKE_DUPLICATE_CHECKSUM')
        sums[name] = sha
    require(set(sums) == set(manifest['files']) | {'run-manifest.json'}
            and all(sha_file(run / name) == sha for name, sha in sums.items()), 'SMOKE_CHECKSUM_LIST')
    config = read_json(run / 'resolved-config.json')
    require(digest(config) == manifest['config_sha256'], 'SMOKE_CONFIG_HASH')
    reference = read_json(run / 'data-reference.json')
    require(reference['manifest_sha256'] == config['data_manifest_sha256']
            == manifest['data_manifest_sha256']
            and reference['contract_sha256'] == config['contract_sha256']
            and (reference['train'], reference['validation'], reference['holdout']) == (128, 32, 0),
            'SMOKE_DATA_IDENTITY')
    args = read_json(run / 'training-arguments.json')
    require(args['max_steps'] == steps and args['fp16'] is True and args['bf16'] is False
            and args['gradient_accumulation_steps'] == 4
            and args['per_device_train_batch_size'] == 1, 'SMOKE_TRAINING_ARGUMENTS')
    env = read_json(run / 'environment.json')
    require(env['cuda_available'] is True and env['cuda'] is not None
            and len(env['gpus']) == 1 and 'T4' in env['gpus'][0], 'SMOKE_GPU_EVIDENCE_REQUIRED')
    devices = read_json(run / 'training-device.json')
    require(devices['visible_gpu_count'] == devices['world_size'] == 1
            and devices['mode'] == 'SINGLE_GPU_NO_DATAPARALLEL', 'SMOKE_SINGLE_GPU_REQUIRED')
    loaded = read_json(run / 'model-load-report.json')
    require(loaded['model_id'] == config['model_id'] and loaded['revision'] == config['revision']
            and loaded['is_loaded_in_4bit'] is True and loaded['use_cache'] is False
            and loaded['quantization']['bnb_4bit_quant_type'] == 'nf4'
            and loaded['quantization']['bnb_4bit_use_double_quant'] is True, 'SMOKE_BASE_LOAD_IDENTITY')
    update = read_json(run / 'adapter-update-report.json')
    require((update['start_global_step'], update['global_step'], update['attempted_updates'],
             update['applied_updates'], update['scaler_skipped_updates'], update['finite_gradient_checks'])
            == (0, steps, steps, steps, 0, steps) and math.isfinite(update['adapter_delta_l2'])
            and update['adapter_delta_l2'] > 0 and update['base_frozen'] is True,
            'SMOKE_OPTIMIZER_PROOF')
    events = read_rows(run / 'optimizer-events.jsonl')
    require([r['step'] for r in events] == list(range(1, steps + 1))
            and all(r['update_applied'] is True for r in events), 'SMOKE_UPDATE_EVENTS')
    logs = read_rows(run / 'train-metrics.jsonl')
    loss = {r['step']: r['loss'] for r in logs if 'loss' in r}
    require(set(loss) == set(range(1, steps + 1)) and all(math.isfinite(v) for v in loss.values()), 'SMOKE_FINITE_LOSS')
    evaluation = read_json(run / 'eval-metrics.json')
    require(math.isfinite(evaluation['eval_loss']), 'SMOKE_FINITE_EVAL_LOSS')
    require(read_json(run / 'storage-check.json')['passed'] is True, 'SMOKE_STORAGE_CHECK')
    parameters = read_json(run / 'trainable-parameters.json')
    require(parameters['base_frozen'] is True and parameters['trainable_parameters'] > 0,
            'SMOKE_BASE_FREEZE')
    required = {'adapter_config.json', 'adapter_model.safetensors', 'trainer_state.json',
                'optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'scaler.pt', 'binding.json'}
    checkpoint = run / ('checkpoint-' + str(steps))
    require(checkpoint.is_dir() and required <= {p.name for p in checkpoint.iterdir()},
            'SMOKE_CHECKPOINT_INCOMPLETE')
    require(read_json(checkpoint / 'trainer_state.json')['global_step'] == steps,
            'SMOKE_CHECKPOINT_STEP')
    binding = read_json(checkpoint / 'binding.json')
    require(binding['config_sha256'] == digest(config)
            and binding['data_manifest_sha256'] == config['data_manifest_sha256'], 'SMOKE_CHECKPOINT_BINDING')
    from safetensors import safe_open
    import torch
    with safe_open(run / 'final-adapter/adapter_model.safetensors', framework='pt', device='cpu') as final, \
         safe_open(checkpoint / 'adapter_model.safetensors', framework='pt', device='cpu') as saved:
        require(set(final.keys()) == set(saved.keys()) and bool(final.keys()), 'SMOKE_SAVED_TENSOR_KEYS')
        count = 0
        for name in final.keys():
            require('lora_' in name, 'SMOKE_UNEXPECTED_ADAPTER_TENSOR')
            tensor = final.get_tensor(name)
            require(torch.isfinite(tensor).all().item() and torch.equal(tensor, saved.get_tensor(name)),
                    'SMOKE_SAVED_TENSORS_DIFFER')
            count += tensor.numel()
    require(count == parameters['trainable_parameters'], 'SMOKE_PARAMETER_COUNT')
    vram = read_json(run / 'vram.json')
    require(0 < vram['peak_allocated_bytes'] <= vram['peak_reserved_bytes'], 'SMOKE_VRAM_METRICS')
    return dict(status='GPU_SMOKE_PASSED' if profile == 'smoke' else 'GPU_PILOT_PASSED',
                global_step=steps, applied_updates=steps,
                scaler_skipped_updates=0, adapter_delta_l2=update['adapter_delta_l2'], base_frozen=True,
                train_loss_by_step=loss, eval_loss=evaluation['eval_loss'],
                trainable_parameters=count, checkpoint=checkpoint.name, saved_adapter_tensors_match=True,
                vram=vram, config_sha256=digest(config), data_manifest_sha256=config['data_manifest_sha256'],
                run_manifest_sha256=sha_file(run / 'run-manifest.json'),
                limitation=('Two-step technical smoke, not pilot 50, reload/resume verification or quality improvement.'
                            if profile == 'smoke' else
                            'Technical pilot 50, not independent GPU reload/resume verification or quality improvement.'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args(argv)
    run = args.run.resolve()
    report = audit(run)
    report_path = run.with_name(run.name + '-audit.json')
    if report_path.exists():
        require(read_json(report_path) == report, 'SMOKE_AUDIT_OUTPUT_DIFFERS')
    else:
        write_json(report_path, report)
    archive = run.with_name(run.name + '.zip')
    require(not archive.exists(), 'SMOKE_ZIP_EXISTS')
    needed = sum(p.stat().st_size for p in run.rglob('*') if p.is_file())
    require(shutil.disk_usage(run.parent).free >= needed + 256 * 1024 ** 2, 'INSUFFICIENT_SPACE_FOR_SMOKE_ZIP')
    with ZipFile(archive, 'x', compression=ZIP_DEFLATED) as zipped:
        for path in sorted(run.rglob('*')):
            if path.is_file():
                zipped.write(path, path.relative_to(run).as_posix())
    write_json(run.with_name(run.name + '-receipt.json'), dict(
        file=archive.name, sha256=sha_file(archive), size_bytes=archive.stat().st_size,
        audit_file=report_path.name, audit_sha256=sha_file(report_path),
        run_manifest_sha256=report['run_manifest_sha256'], model_revision=read_json(run / 'resolved-config.json')['revision'],
        global_step=2, scope='PRIVATE_GPU_SMOKE_HANDOFF', base_weights_included=False))
    print('GPU_SMOKE_PASSED: ' + str(report_path))
    print('Private artifact: ' + str(archive))
    return 0


if __name__ == '__main__':
    sys.exit(main())
