"""Authenticate and unpack private handoffs without executing their payloads."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import stat
from zipfile import ZipFile

from .data import loads, read_json, require, sha_file, within
from .runtime import inventory, verify_inventory, write_json


def extract_package(archive, receipt, output, *, manifest_name='manifest.json'):
    archive, output = Path(archive), Path(output)
    require(archive.stat().st_size == receipt['size_bytes'] and sha_file(archive) == receipt['sha256'], 'ZIP_RECEIPT')
    with ZipFile(archive) as zipped:
        entries = zipped.infolist()
        names = [entry.filename for entry in entries]
        require(len(entries) <= 2000 and len(names) == len(set(name.casefold() for name in names))
                and sum(entry.file_size for entry in entries) <= 4 * 1024**3, 'ZIP_LIMITS')
        for entry in entries:
            require(not entry.is_dir() and not stat.S_ISLNK(entry.external_attr >> 16)
                    and PurePosixPath(entry.filename).as_posix() == entry.filename
                    and '..' not in PurePosixPath(entry.filename).parts, 'UNSAFE_ZIP_MEMBER')
            within(output, entry.filename)
        manifest_bytes = zipped.read(manifest_name)
        expected = receipt.get('manifest_sha256', receipt.get('run_manifest_sha256'))
        require(expected and hashlib.sha256(manifest_bytes).hexdigest() == expected, 'ZIP_MANIFEST_HASH')
        manifest = loads(manifest_bytes.decode('utf-8'))
        extras = {manifest_name}
        if 'SHA256SUMS.txt' in names:
            extras.add('SHA256SUMS.txt')
        require(set(names) == set(manifest['files']) | extras, 'ZIP_FILE_SET')
        for name, info in manifest['files'].items():
            entry = zipped.getinfo(name)
            require(entry.file_size == info['size_bytes'], 'ZIP_MEMBER_SIZE')
            digest = hashlib.sha256()
            with zipped.open(entry) as stream:
                for block in iter(lambda: stream.read(1024**2), b''):
                    digest.update(block)
            require(digest.hexdigest() == info['sha256'], 'ZIP_MEMBER_HASH:' + name)
        if output.exists():
            require(set(inventory(output)) == set(names), 'RECEIVED_FILE_SET')
            verify_inventory(output, manifest['files'])
            require((output / manifest_name).read_bytes() == manifest_bytes, 'RECEIVED_MANIFEST')
        else:
            output.mkdir(parents=True)
            for entry in entries:
                target = within(output, entry.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(entry) as stream, target.open('xb') as destination:
                    shutil.copyfileobj(stream, destination)
            verify_inventory(output, manifest['files'])
    return dict(passed=True, archive_sha256=receipt['sha256'], manifest_sha256=expected,
                files_checked=len(manifest['files']), payloads_executed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--manifest-name', default='manifest.json')
    args = parser.parse_args()
    require(not args.report.resolve().is_relative_to(args.output.resolve()), 'REPORT_OUTSIDE_RECEIVED_PACKAGE')
    report = extract_package(args.archive, read_json(args.receipt), args.output, manifest_name=args.manifest_name)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print('HANDOFF_AUTHENTICATED', report['files_checked'], 'files')


if __name__ == '__main__':
    main()
