import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.qlora.receive import extract_package


class ReceiveTests(unittest.TestCase):
    def fixture(self, folder, name='run/config.json'):
        content = b'{"steps":50}'
        manifest = json.dumps({'files': {name: {'sha256': hashlib.sha256(content).hexdigest(),
                                               'size_bytes': len(content)}}}).encode()
        archive = folder / 'source.zip'
        with ZipFile(archive, 'w') as zipped:
            zipped.writestr(name, content)
            zipped.writestr('manifest.json', manifest)
        receipt = dict(sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), size_bytes=archive.stat().st_size,
                       manifest_sha256=hashlib.sha256(manifest).hexdigest())
        return archive, receipt

    def test_authenticates_every_file_and_can_read_back_same_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, receipt = self.fixture(root)
            output = root / 'received'
            report = extract_package(archive, receipt, output)
            self.assertEqual(report['files_checked'], 1)
            self.assertEqual((output / 'run/config.json').read_bytes(), b'{"steps":50}')
            self.assertEqual(extract_package(archive, receipt, output), report)

    def test_bad_receipt_rejected_before_output_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, receipt = self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'ZIP_RECEIPT'):
                extract_package(archive, {**receipt, 'sha256': '0'*64}, root / 'received')
            self.assertFalse((root / 'received').exists())

    def test_traversal_rejected_even_if_hashes_are_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, receipt = self.fixture(root, '../outside.json')
            with self.assertRaises(ValueError):
                extract_package(archive, receipt, root / 'received')
            self.assertFalse((root / 'outside.json').exists())

    def test_unlisted_file_in_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, receipt = self.fixture(root)
            with ZipFile(archive, 'a') as zipped:
                zipped.writestr('.env', 'sensitive fixture')
            receipt.update(sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), size_bytes=archive.stat().st_size)
            with self.assertRaisesRegex(ValueError, 'ZIP_FILE_SET'):
                extract_package(archive, receipt, root / 'received')


if __name__ == '__main__':
    unittest.main()
