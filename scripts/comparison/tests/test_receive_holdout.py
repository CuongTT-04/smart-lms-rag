import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.comparison.protocol import write_json
from scripts.comparison.receive_holdout import MEMBERS, authenticate


class ReceiveHoldoutTests(unittest.TestCase):
    def fixture(self, root, *, extra=False, tamper=False):
        report = dict(rows=232, status='fixture')
        files = {name: b'fixture' for name in MEMBERS - {'artifacts.json'}}
        files['audit.json'] = json.dumps(report).encode()
        manifest = {name: dict(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                    for name, raw in files.items() if name != 'console.log'}
        files['artifacts.json'] = json.dumps(manifest).encode()
        if tamper:
            files['outputs.jsonl'] = b'tampered'
        if extra:
            files['../outside'] = b'bad'
        archive = root / 'fixture.zip'
        with ZipFile(archive, 'w') as zipped:
            for name, raw in files.items():
                zipped.writestr(name, raw)
        receipt = root / 'receipt.json'
        audit = root / 'audit.json'
        write_json(receipt, dict(archive=archive.name, sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                                size_bytes=archive.stat().st_size, process_exit_code=0, audit=report))
        write_json(audit, report)
        return archive, receipt, audit

    def test_valid_transport(self):
        with tempfile.TemporaryDirectory() as temporary:
            files, _ = authenticate(*self.fixture(Path(temporary)))
            self.assertEqual(set(files), MEMBERS)

    def test_archive_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive, receipt, audit = self.fixture(Path(temporary))
            with archive.open('ab') as stream:
                stream.write(b'tampered')
            with self.assertRaisesRegex(ValueError, 'HOLDOUT_RECEIPT'):
                authenticate(archive, receipt, audit)

    def test_unexpected_or_unsafe_member(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'HOLDOUT_ARCHIVE_MEMBERS'):
                authenticate(*self.fixture(Path(temporary), extra=True))

    def test_payload_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'HOLDOUT_ARTIFACT_HASH'):
                authenticate(*self.fixture(Path(temporary), tamper=True))

    def test_external_audit_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive, receipt, audit = self.fixture(Path(temporary))
            write_json(audit, dict(rows=231))
            with self.assertRaisesRegex(ValueError, 'HOLDOUT_AUDIT_COPIES'):
                authenticate(archive, receipt, audit)
