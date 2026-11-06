"""Run the versioned trainer in a fresh, separate Kaggle Python environment."""
import argparse
from importlib.metadata import version
import os
from pathlib import Path
import subprocess
import sys

from .data import require


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', choices=('smoke', 'pilot'), required=True)
    parser.add_argument('--environment', type=Path, default=Path('/kaggle/working/qlora-env'))
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[2] / 'configs/qlora-pilot.json')
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--environment-only', action='store_true', help='Check CUDA, NF4 and data; never train Qwen')
    parser.add_argument('--allow-model-download', action='store_true')
    parser.add_argument('--resume-from-checkpoint', type=Path)
    parser.add_argument('--resume-manifest-sha256')
    parser.add_argument('--stop-after-step', type=int)
    args = parser.parse_args(argv)
    require(not args.environment_only or (not args.preflight_only and not args.allow_model_download
            and args.resume_from_checkpoint is None and args.resume_manifest_sha256 is None
            and args.stop_after_step is None), 'ENVIRONMENT_ONLY_ARGUMENT_CONFLICT')
    require(sys.platform == 'linux' and Path('/kaggle/working').is_dir(), 'KAGGLE_ONLY')
    require(args.environment.resolve().is_relative_to(Path('/kaggle/working')),
            'ENVIRONMENT_MUST_STAY_IN_KAGGLE_WORKING')
    require(not args.output.exists(), 'OUTPUT_ALREADY_EXISTS')
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, USE_TF='0', USE_FLAX='0', TOKENIZERS_PARALLELISM='false',
               CUDA_VISIBLE_DEVICES='0',
               PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', WANDB_DISABLED='true')
    python = args.environment / 'bin/python'
    # Re-create the interpreter/config in place even after a partial failed venv.
    # Kaggle's system Python may not support ensurepip; target it with host pip.
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', '--system-site-packages',
                    str(args.environment)], check=True, env=env)
    require(python.is_file(), 'TRAINING_ENVIRONMENT_INCOMPLETE')
    torch_version = version('torch')
    constraint = args.environment / 'torch-constraint.txt'
    constraint.write_text('torch==' + torch_version + '\n', encoding='utf-8')
    subprocess.run([sys.executable, '-m', 'pip', '--python', str(python),
                    'install', '--disable-pip-version-check',
                    '--constraint', str(constraint),
                    '-r', str(Path(__file__).parent / 'requirements.txt')], check=True, env=env)
    installed_torch = subprocess.run([str(python), '-c',
        'from importlib.metadata import version; print(version("torch"))'],
        check=True, capture_output=True, text=True, env=env).stdout.strip()
    require(installed_torch == torch_version, 'KAGGLE_CUDA_TORCH_CHANGED')
    module = 'scripts.qlora.setup' if args.environment_only else 'scripts.qlora.train'
    command = [str(python), '-B', '-m', module, '--bundle', str(args.bundle.resolve()),
               '--config', str(args.config.resolve()), '--output', str(args.output.resolve()),
               *([] if args.environment_only else ['--profile', args.profile])]
    for flag, enabled in (('--preflight-only', args.preflight_only),
                           ('--allow-model-download', args.allow_model_download)):
        if enabled:
            command.append(flag)
    for name in ('resume_from_checkpoint', 'resume_manifest_sha256', 'stop_after_step'):
        if getattr(args, name) is not None:
            command.extend(['--' + name.replace('_', '-'), str(getattr(args, name))])
    subprocess.run(command, check=True, env=env, cwd=root)
    return 0


if __name__ == '__main__':
    sys.exit(main())
