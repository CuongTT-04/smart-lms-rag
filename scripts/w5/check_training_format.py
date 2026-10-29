"""Run in the pinned tokenizer-only environment; never loads model weights."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.w5.cli import run, training_main

if __name__=='__main__':
    raise SystemExit(run(training_main))
