"""Separate Kaggle CUDA environment for expanded training; no ensurepip required."""
import argparse
from importlib.metadata import version
import os
from pathlib import Path
import subprocess
import sys

from scripts.qlora.data import require


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--environment',type=Path,default=Path('/kaggle/working/comparison-training-env'))
    args=parser.parse_args()
    require(sys.platform=='linux' and Path('/kaggle/working').is_dir(),'KAGGLE_ONLY')
    require(args.environment.resolve().is_relative_to(Path('/kaggle/working')),'KAGGLE_ENVIRONMENT_PATH')
    env=dict(os.environ,USE_TF='0',USE_FLAX='0',CUDA_VISIBLE_DEVICES='0',PYTHONUTF8='1',
             PYTHONDONTWRITEBYTECODE='1',TOKENIZERS_PARALLELISM='false',WANDB_DISABLED='true')
    subprocess.run([sys.executable,'-m','venv','--without-pip','--system-site-packages',str(args.environment)],check=True,env=env)
    python=args.environment/'bin/python'
    before=version('torch')
    constraint=args.environment/'torch-constraint.txt'
    constraint.write_text('torch=='+before+'\n',encoding='utf-8')
    subprocess.run([sys.executable,'-m','pip','--python',str(python),'install','--disable-pip-version-check',
        '--constraint',str(constraint),'-r',str(args.package/'scripts/comparison/training-requirements.txt')],check=True,env=env)
    after=subprocess.run([str(python),'-c','from importlib.metadata import version; print(version("torch"))'],
        capture_output=True,text=True,check=True,env=env).stdout.strip()
    require(before==after,'KAGGLE_CUDA_TORCH_CHANGED')
    subprocess.run([str(python),'-B','-m','scripts.comparison.training','--package',str(args.package),
        '--output','/kaggle/working/unused-training-preflight','--check-only'],cwd=args.package,check=True,env=env)


if __name__=='__main__':
    main()
