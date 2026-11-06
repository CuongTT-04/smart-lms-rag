"""GPU environment checks only: no Qwen weights, LoRA training or optimizer steps."""
import argparse
import gc
from importlib.metadata import version
import os
from pathlib import Path
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout

from .collator import CompletionCollator
from .data import load_pilot, read_json, require
from .runtime import environment, finish_manifest, output_guard, write_json


def check_hardware(torch, working):
    require(torch.cuda.is_available(), 'CUDA_REQUIRED')
    require(torch.cuda.device_count() == 1, 'SINGLE_VISIBLE_GPU_REQUIRED_NO_DATAPARALLEL')
    require(torch.version.cuda is not None, 'CUDA_TORCH_REQUIRED_NOT_CPU_WHEEL')
    require('T4' in torch.cuda.get_device_name(0), 'PROFILE_REQUIRES_T4')
    free, total = torch.cuda.mem_get_info(0)
    require(free >= 12 * 1024 ** 3, 'GPU_BUSY_OR_INSUFFICIENT_FREE_VRAM')
    disk = shutil.disk_usage(working)
    # This phase writes small reports/tensors only; base-cache budgeting belongs
    # to the weight-loading phase and must not be reported as verified here.
    require(disk.free >= 1024 ** 3, 'NEED_1_GIB_FREE_FOR_ENVIRONMENT_CHECK')
    return dict(device=torch.cuda.get_device_name(0), free_vram_bytes=free,
                total_vram_bytes=total, free_working_disk_bytes=disk.free,
                free_working_disk_gib=round(disk.free / 1024 ** 3, 3),
                training_storage_check='PENDING_BEFORE_BASE_WEIGHT_LOADING')


def probe_nf4(torch):
    import bitsandbytes as bnb
    # A random frozen layer tests CUDA kernels, not Qwen or an optimizer update.
    torch.manual_seed(42)
    with torch.cuda.device(0):
        layer = bnb.nn.Linear4bit(64, 64, bias=False, compute_dtype=torch.float16,
                                  compress_statistics=True, quant_type='nf4')
        layer.requires_grad_(False)
        layer = layer.to('cuda:0')
        sample = torch.randn(2, 64, device='cuda:0', dtype=torch.float16, requires_grad=True)
        output = layer(sample)
        require(output.dtype == torch.float16 and torch.isfinite(output).all().item(), 'NF4_FP16_FORWARD')
        output.float().square().mean().backward()
        require(sample.grad is not None and torch.isfinite(sample.grad).all().item()
                and sample.grad.abs().sum().item() > 0, 'NF4_INPUT_GRADIENT')
        state = layer.weight.quant_state
        require(layer.weight.device.type == 'cuda' and state.quant_type == 'nf4'
                and state.nested, 'NF4_DOUBLE_QUANTIZATION')
        torch.cuda.synchronize(0)
        del sample, output, layer
    gc.collect()
    torch.cuda.empty_cache()
    return dict(nf4_cuda_forward='PASSED', fp16_compute='PASSED', input_backward='PASSED',
                double_quantization=True, optimizer_steps=0, qwen_weights_loaded=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    os.environ.update(USE_TF='0', USE_FLAX='0', TOKENIZERS_PARALLELISM='false',
                      PYTHONDONTWRITEBYTECODE='1', WANDB_DISABLED='true')
    config = read_json(args.config)
    output = output_guard(args.output, [args.bundle, args.config])
    output.mkdir(parents=True, exist_ok=False)
    status, error = 'FAILED', None
    try:
        with (output / 'setup-output.txt').open('w', encoding='utf-8') as stream, \
             redirect_stdout(stream), redirect_stderr(stream):
            import torch
            from packaging.version import Version
            write_json(output / 'environment.json', environment())
            require(Version(torch.__version__.split('+')[0]) >= Version('2.6'), 'TORCH_2_6_OR_NEWER_REQUIRED')
            for name, expected in config['dependencies'].items():
                require(version(name) == expected, 'DEPENDENCY_VERSION:' + name)
            hardware = check_hardware(torch, output)
            from transformers import Trainer, TrainingArguments
            from peft import LoraConfig, prepare_model_for_kbit_training
            from accelerate import Accelerator
            probe = probe_nf4(torch)
            data, tokenizer, contract = load_pilot(args.bundle / 'data/pilot-v2',
                                                   args.bundle / 'tokenizer', config)
            collator = CompletionCollator()
            for rows in data.values():
                for offset in range(0, len(rows), 4):
                    collator(rows[offset:offset + 4])
            write_json(output / 'environment-check.json', dict(
                status='ENVIRONMENT_READY_FOR_SMOKE', hardware=hardware, kernel_probe=probe,
                records_checked=sum(map(len, data.values())), train=len(data['train']),
                validation=len(data['validation']), qwen_weights_loaded=False,
                qwen_training='NOT_RUN', gpu_smoke='NOT_RUN', gpu_pilot='NOT_RUN'))
            status = 'ENVIRONMENT_READY_FOR_SMOKE'
    except BaseException as exc:
        error = type(exc).__name__
        write_json(output / 'environment-check.json', dict(status='FAILED', error_type=error,
                   error=str(exc), qwen_training='NOT_RUN', gpu_smoke='NOT_RUN', gpu_pilot='NOT_RUN'))
        raise
    finally:
        finish_manifest(output, status=status, profile='environment-only', config=config, error_type=error)
    print(status + ': ' + str(output))
    return 0


if __name__ == '__main__':
    sys.exit(main())
