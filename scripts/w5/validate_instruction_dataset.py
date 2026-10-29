"""Run: python scripts/w5/validate_instruction_dataset.py --help."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.w5.cli import run, validate_main

if __name__=='__main__':
    raise SystemExit(run(validate_main))
