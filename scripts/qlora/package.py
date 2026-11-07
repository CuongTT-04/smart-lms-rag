"""Package only trainer source, tests, recipe and the single guide for Kaggle."""
import argparse
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from .data import sha_file
from .runtime import output_guard, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New private directory')
    parser.add_argument('--pilot-archive', type=Path, help='Also build one private Input ZIP for environment setup')
    args = parser.parse_args(argv)
    if args.pilot_archive:
        from .data import require
        require(sha_file(args.pilot_archive) == '2b44e35f7386b506955e9fad29541490c052129a8af6ae0eef7e4f0b7f7c0707',
                'LOCKED_PILOT_ARCHIVE_HASH')
    root = Path(__file__).resolve().parents[2]
    output = output_guard(args.output, [root / 'scripts/qlora', root / 'configs', root / 'docs'])
    output.mkdir(parents=True, exist_ok=False)
    paths = sorted((root / 'scripts/qlora').rglob('*.py')) + [
        root / 'scripts/qlora/requirements.txt', root / 'configs/qlora-pilot.json', root / 'docs/qlora.md']
    archive = output / 'qlora-tools.zip'
    with ZipFile(archive, 'x', compression=ZIP_DEFLATED) as zipped:
        for path in paths:
            zipped.write(path, path.relative_to(root).as_posix())
    write_json(output / 'qlora-tools.receipt.json', {
        'file': archive.name, 'sha256': sha_file(archive), 'size_bytes': archive.stat().st_size,
        'files': {p.relative_to(root).as_posix(): sha_file(p) for p in paths},
        'data_included': False, 'model_weights_included': False,
        'gpu_smoke': 'NOT_RUN', 'gpu_pilot': 'NOT_RUN'})
    if args.pilot_archive:
        kit = output / 'qlora-environment-input.zip'
        # Inner archives use .bundle so upload services do not unpack them recursively.
        with ZipFile(kit, 'x', compression=ZIP_DEFLATED) as zipped:
            zipped.write(archive, 'tools.bundle')
            zipped.write(args.pilot_archive, 'pilot.bundle')
        write_json(output / 'qlora-environment-input.receipt.json', {
            'file': kit.name, 'sha256': sha_file(kit), 'size_bytes': kit.stat().st_size,
            'inner_archives': {'tools.bundle': sha_file(archive), 'pilot.bundle': sha_file(args.pilot_archive)},
            'scope': 'PRIVATE_INTERNAL_ENVIRONMENT_SETUP', 'public_redistribution_allowed': False,
            'qwen_weights_included': False, 'gpu_check': 'NOT_RUN'})
    print(str(archive))
    return 0


if __name__ == '__main__':
    sys.exit(main())
