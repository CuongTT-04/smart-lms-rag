"""Run CPU trainer tests and optional real-tokenizer pilot preflight; no Qwen weights."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import os
from pathlib import Path
import sys
import time
import unittest

from .data import read_json
from .runtime import environment, finish_manifest, output_guard, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[2] / 'configs/qlora-pilot.json')
    args = parser.parse_args(argv)
    os.environ.update(USE_TF='0', USE_FLAX='0', HF_HUB_OFFLINE='1',
                      TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false', WANDB_DISABLED='true')
    config = read_json(args.config)
    output = output_guard(args.output, [args.config] + ([args.bundle] if args.bundle else []))
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    status = 'FAILED'
    error = None
    try:
        with (output / 'test-results.txt').open('w', encoding='utf-8') as stream, \
             redirect_stdout(stream), redirect_stderr(stream):
            suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent / 'tests'),
                top_level_dir=str(Path(__file__).resolve().parents[2]))
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
            write_json(output / 'tests.json', {
                'tests_run': result.testsRun, 'failures': len(result.failures),
                'errors': len(result.errors), 'skipped': len(result.skipped),
                'passed': result.wasSuccessful(), 'seconds': time.monotonic() - start,
                'scope': 'CPU unit tests and tiny random Qwen2 LoRA integration, not 7B QLoRA smoke',
                'qwen_7b_weights_loaded': False, 'gpu_smoke': 'NOT_RUN', 'gpu_pilot': 'NOT_RUN'})
            if not result.wasSuccessful():
                return 1
            from .tests.test_runtime import RuntimeTests
            write_json(output / 'tiny-cpu-proof.json', RuntimeTests.cpu_proof)
            if args.bundle:
                from .train import main as preflight
                preflight(['--config', str(args.config), '--bundle', str(args.bundle),
                           '--profile', 'smoke', '--preflight-only', '--output', str(output / 'pilot-preflight')])
            write_json(output / 'environment.json', environment())
            status = 'CPU_CHECKS_PASSED'
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        finish_manifest(output, status=status, profile='cpu-tests', config=config, error_type=error)
    print(status + ': ' + str(output))
    return 0


if __name__ == '__main__':
    sys.exit(main())
