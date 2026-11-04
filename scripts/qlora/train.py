"""CLI: CPU preflight, separate T4 smoke/pilot runs, and authenticated resume."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import os
from pathlib import Path
import sys

from .collator import CompletionCollator
from .data import load_pilot, read_json, require
from .runtime import (environment, finish_manifest, fit, load_training_model, output_guard,
                      parameter_report, resume_checkpoint, training_arguments, validate_recipe, write_json)
from .storage import check_training_storage


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True, help='Extracted immutable handoff root')
    parser.add_argument('--profile', choices=('smoke', 'pilot'), required=True)
    parser.add_argument('--output', type=Path, required=True, help='New private run directory')
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--allow-model-download', action='store_true')
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--resume-from-checkpoint', type=Path)
    parser.add_argument('--resume-manifest-sha256')
    parser.add_argument('--stop-after-step', type=int)
    args = parser.parse_args(argv)
    os.environ.update(USE_TF='0', USE_FLAX='0', TOKENIZERS_PARALLELISM='false', WANDB_DISABLED='true')
    os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')
    config = read_json(args.config)
    validate_recipe(config, args.profile)
    inputs = [args.bundle, args.config]
    if args.resume_from_checkpoint:
        inputs.append(args.resume_from_checkpoint.parent)
    output = output_guard(args.output, inputs)
    require(args.resume_from_checkpoint is not None or (args.stop_after_step is None
            and args.resume_manifest_sha256 is None), 'RESUME_ARGUMENTS_REQUIRED')
    require(not args.preflight_only or args.resume_from_checkpoint is None, 'PREFLIGHT_NOT_RESUME')
    resume = None
    if args.resume_from_checkpoint:
        require(args.profile == 'pilot', 'RESUME_PILOT_ONLY')
        resume = resume_checkpoint(args.resume_from_checkpoint, args.resume_manifest_sha256,
                                    config, args.stop_after_step)
    output.mkdir(parents=True, exist_ok=False)
    status, error = 'FAILED', None
    def phase(name):
        write_json(output / 'phase.json', {'phase': name, 'profile': args.profile})
    try:
        phase('VALIDATING_DATA')
        with (output / 'stdout.txt').open('w', encoding='utf-8') as stdout, \
             (output / 'stderr.txt').open('w', encoding='utf-8') as stderr, \
             redirect_stdout(stdout), redirect_stderr(stderr):
            import torch
            from transformers import set_seed
            set_seed(config['seed'])
            write_json(output / 'resolved-config.json', config)
            source = output / 'source/qlora'
            source.mkdir(parents=True)
            for code in Path(__file__).parent.glob('*.py'):
                (source / code.name).write_bytes(code.read_bytes())
            actual_environment = environment()
            write_json(output / 'environment.json', actual_environment)
            (output / 'requirements-resolved.txt').write_text(''.join(
                name + '==' + ver + '\n' for name, ver in sorted(
                    actual_environment['dependencies'].items())), encoding='utf-8')
            write_json(output / 'data-reference.json', {
                'manifest_sha256': config['data_manifest_sha256'],
                'contract_sha256': config['contract_sha256'],
                'train': 128, 'validation': 32, 'holdout': 0,
                'resume_checkpoint': str(resume) if resume else None,
                'resume_manifest_sha256': args.resume_manifest_sha256})
            data, tokenizer, contract = load_pilot(args.bundle / 'data/pilot-v2',
                                                   args.bundle / 'tokenizer', config)
            collator = CompletionCollator()
            shapes = []
            for split, rows in data.items():
                for start in range(0, len(rows), 4):
                    batch = collator(rows[start:start + 4])
                    shapes.append(list(batch['input_ids'].shape))
            write_json(output / 'preflight.json', {
                'passed': True, 'records_checked': sum(map(len, data.values())),
                'batch_shapes': shapes, 'tensor_dtype': 'torch.int64',
                'tokenizer_recomputed': True, 'model_weights_loaded': False,
                'training': 'NOT_RUN'})
            if args.preflight_only:
                status = 'PREFLIGHT_PASSED'
            else:
                from huggingface_hub.constants import HF_HUB_CACHE
                cache = args.cache_dir or Path(HF_HUB_CACHE)
                phase('CHECKING_TRAINING_STORAGE')
                storage = check_training_storage(config, cache, output,
                                                   allow_download=args.allow_model_download)
                write_json(output / 'storage-check.json', storage)
                require(storage['passed'], 'INSUFFICIENT_DISK_FOR_PINNED_BASE_AND_RUN')
                phase('LOADING_PINNED_BASE')
                model = load_training_model(config, allow_download=args.allow_model_download,
                                             cache_dir=cache)
                base = model.get_base_model()
                quantization = base.config.quantization_config
                write_json(output / 'model-load-report.json', {
                    'model_id': config['model_id'], 'revision': base.config._commit_hash,
                    'model_class': type(base).__name__, 'is_loaded_in_4bit': base.is_loaded_in_4bit,
                    'quantization': quantization.to_dict() if hasattr(quantization, 'to_dict') else quantization,
                    'use_cache': base.config.use_cache})
                torch.cuda.reset_peak_memory_stats(0)
                write_json(output / 'trainable-parameters.json', parameter_report(model))
                train_args = training_arguments(config, args.profile, output)
                write_json(output / 'training-arguments.json', train_args.to_dict())
                write_json(output / 'training-device.json', {
                    'visible_gpu_count': train_args.n_gpu, 'world_size': train_args.world_size,
                    'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
                    'mode': 'SINGLE_GPU_NO_DATAPARALLEL'})
                phase('TRAINING_AND_VALIDATION')
                _, update = fit(model, data, collator, train_args, output, config,
                                 resume=resume, stop_after_step=args.stop_after_step)
                phase('SAVING_ARTIFACTS')
                write_json(output / 'vram.json', {
                    'peak_allocated_bytes': torch.cuda.max_memory_allocated(0),
                    'peak_reserved_bytes': torch.cuda.max_memory_reserved(0)})
                tokenizer.save_pretrained(output / 'tokenizer')
                write_json(output / 'tokenizer-reference.json', read_json(
                    args.bundle / 'data/pilot-v2/tokenizer-reference.json'))
                status = 'TRAINING_COMPLETED'
            phase(status)
    except BaseException as exc:
        error = type(exc).__name__
        phase('FAILED')
        # Do not print payloads or secrets into public console output.
        with (output / 'stderr.txt').open('a', encoding='utf-8') as stream:
            stream.write(error + ': ' + str(exc) + '\n')
        raise
    finally:
        finish_manifest(output, status=status, profile=args.profile, config=config, error_type=error)
    print(status + ': ' + str(output))
    return 0


if __name__ == '__main__':
    sys.exit(main())
