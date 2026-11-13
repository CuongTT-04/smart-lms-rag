from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.comparison.intake_main import FILES, authenticate
from scripts.comparison.protocol import write_json
from scripts.qlora.data import sha_file


class IntakeMainTests(unittest.TestCase):
    def fixture(self, root, files=None):
        archive = root / 'main.zip'
        audit = {'rows': 900}
        with ZipFile(archive, 'x') as zipped:
            for name in (FILES if files is None else files):
                zipped.writestr(name, '{"rows":900}' if name == 'audit.json' else '{}')
        receipt = root / 'receipt.json'
        audit_file = root / 'audit.json'
        write_json(receipt, dict(archive=archive.name, sha256=sha_file(archive),
            size_bytes=archive.stat().st_size, process_exit_code=0, audit=audit))
        write_json(audit_file, audit)
        return archive, receipt, audit_file

    def test_authenticates_exact_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp))
            payload, _ = authenticate(*args)
            self.assertEqual(set(payload), FILES)

    def test_rejects_changed_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp))
            args[0].write_bytes(args[0].read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_RECEIPT'):
                authenticate(*args)

    def test_rejects_missing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp), FILES - {'outputs.jsonl'})
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_FILES'):
                authenticate(*args)

    def test_rejects_unexpected_archive_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp), FILES | {'../outside'})
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_FILES'):
                authenticate(*args)

    def test_rejects_changed_external_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp))
            write_json(args[2], {'rows': 899})
            with self.assertRaisesRegex(ValueError, 'AUDIT_COPIES'):
                authenticate(*args)

    def test_rejects_failed_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture(Path(tmp))
            write_json(args[1], dict(archive=args[0].name, sha256=sha_file(args[0]),
                size_bytes=args[0].stat().st_size, process_exit_code=1, audit={'rows': 900}))
            with self.assertRaisesRegex(ValueError, 'PROCESS_FAILED'):
                authenticate(*args)
