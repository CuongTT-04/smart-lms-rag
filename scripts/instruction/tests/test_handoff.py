import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from scripts.instruction.verify_handoff import safe_name, verify


class HandoffTests(unittest.TestCase):
    def package(self, folder, *, modified=False, extra=False, duplicate=False, approved=False):
        path = Path(folder) / 'handoff.zip'
        content = b'private fixture, not a real instruction record'
        manifest = {'scope': 'MEMBER_A_PRIVATE_INTERNAL_RESEARCH',
                    'final_b_review': 'APPROVED' if approved else 'PENDING', 'group_release_ready': False,
                    'files': {'data.jsonl': {'sha256': hashlib.sha256(content).hexdigest(),
                                             'size_bytes': len(content)}}}
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('handoff-manifest.json', json.dumps(manifest))
            archive.writestr('data.jsonl', b'changed' if modified else content)
            if extra:
                archive.writestr('unexpected.txt', 'extra')
            if duplicate:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    archive.writestr('data.jsonl', content)
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_valid_archive_without_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            path, checksum = self.package(folder)
            self.assertEqual(verify(path, checksum)['file_count'], 1)
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_separate_archive_hash_required(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _ = self.package(folder)
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_CHECKSUM_MISMATCH'):
                verify(path, '0' * 64)

    def test_changed_payload_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path, checksum = self.package(folder, modified=True)
            with self.assertRaisesRegex(ValueError, 'FILE_CHECKSUM_MISMATCH'):
                verify(path, checksum)

    def test_extra_and_duplicate_entries_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for option, message in [('extra', 'ARCHIVE_INVENTORY_MISMATCH'),
                                    ('duplicate', 'DUPLICATE_ARCHIVE_ENTRY')]:
                path, checksum = self.package(folder, **{option: True})
                with self.assertRaisesRegex(ValueError, message):
                    verify(path, checksum)

    def test_windows_and_traversal_paths_rejected(self):
        for name in ('../x', '/x', 'C:/x', 'a\\b', 'a//b', './a', 'x:stream', '',
                     'CON.txt', 'a/nul', 'a./b', 'x /b', 'a\x00b', 'x?y'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'UNSAFE_ARCHIVE_PATH'):
                safe_name(name)

    def test_cannot_turn_handoff_into_peer_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            path, checksum = self.package(folder, approved=True)
            with self.assertRaisesRegex(ValueError, 'UNEXPECTED_APPROVAL_STATUS'):
                verify(path, checksum)
