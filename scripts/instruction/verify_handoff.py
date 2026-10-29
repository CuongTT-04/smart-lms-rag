"""Check a private handoff ZIP without extracting or executing its contents."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


def require(condition, code):
    if not condition:
        raise ValueError(code)


def safe_name(name):
    path = PurePosixPath(name)
    reserved = {'con', 'prn', 'aux', 'nul'} | {f'{prefix}{i}' for prefix in ('com', 'lpt') for i in range(1, 10)}
    require(bool(name) and '\\' not in name and ':' not in name and
            not path.is_absolute() and all(part not in ('', '.', '..') and
                part == part.rstrip(' .') and part.split('.')[0].lower() not in reserved and
                not any(ord(char) < 32 or char in '<>"|?*' for char in part)
                for part in name.split('/')),
            'UNSAFE_ARCHIVE_PATH')
    return name


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def verify(path, expected_sha256):
    require(re.fullmatch(r'[0-9a-f]{64}', expected_sha256) is not None, 'INVALID_EXPECTED_SHA256')
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    require(digest.hexdigest() == expected_sha256, 'ARCHIVE_CHECKSUM_MISMATCH')
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [safe_name(info.filename) for info in infos]
        require(len(names) == len({name.casefold() for name in names}), 'DUPLICATE_ARCHIVE_ENTRY')
        require(len(infos) <= 2000 and sum(info.file_size for info in infos) <= 256 * 1024 * 1024,
                'ARCHIVE_LIMIT_EXCEEDED')
        for info in infos:
            require(not info.is_dir() and ((info.external_attr >> 16) & 0o170000) != 0o120000,
                    'ARCHIVE_LINK_OR_DIRECTORY')
        manifest = json.loads(archive.read('handoff-manifest.json'), object_pairs_hook=unique_object)
        require(manifest['scope'] == 'MEMBER_A_PRIVATE_INTERNAL_RESEARCH', 'INVALID_HANDOFF_SCOPE')
        require(manifest['final_b_review'] == 'PENDING' and manifest['group_release_ready'] is False,
                'UNEXPECTED_APPROVAL_STATUS')
        files = manifest['files']
        require(isinstance(files, dict) and set(names) == set(files) | {'handoff-manifest.json'},
                'ARCHIVE_INVENTORY_MISMATCH')
        for name, entry in files.items():
            safe_name(name)
            content = archive.read(name)
            require(len(content) == entry['size_bytes'] and
                    hashlib.sha256(content).hexdigest() == entry['sha256'], 'FILE_CHECKSUM_MISMATCH')
    return {'status': 'PASSED', 'scope': 'ARCHIVE_INTEGRITY_ONLY_NOT_CONTENT_APPROVAL',
            'file_count': len(files), 'archive_sha256': digest.hexdigest(),
            'final_b_review': 'PENDING', 'group_release_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True, help='Expected hash received separately from the ZIP')
    args = parser.parse_args()
    try:
        result = verify(args.archive, args.sha256)
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.exit(1, f'{type(error).__name__}: {error}\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
