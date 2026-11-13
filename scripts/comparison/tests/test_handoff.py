from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from scripts.comparison.package_handoff import VERIFY
from scripts.comparison.protocol import write_bundle


class HandoffTests(unittest.TestCase):
    def fixture(self, root):
        contents=root/'contents';contents.mkdir()
        (contents/'verify.py').write_text(VERIFY,encoding='utf-8')
        (contents/'result.json').write_bytes(b'{"rows":900}')
        archive=root/'handoff.zip'
        write_bundle(contents,archive)
        extracted=root/'extracted'
        with ZipFile(archive) as zipped:zipped.extractall(extracted)
        return extracted

    def check(self, folder):
        return subprocess.run([sys.executable,'-X','utf8','-B',str(folder/'verify.py')],
            capture_output=True,text=True,encoding='utf-8',errors='replace')

    def test_standalone_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=self.check(self.fixture(Path(tmp)))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('HANDOFF_BYTE_INTEGRITY_PASSED',result.stdout)

    def test_changed_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            extracted=self.fixture(Path(tmp))
            (extracted/'result.json').write_bytes(b'{"rows":899}')
            self.assertNotEqual(self.check(extracted).returncode,0)

    def test_unlisted_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            extracted=self.fixture(Path(tmp))
            (extracted/'extra.txt').write_bytes(b'extra')
            self.assertNotEqual(self.check(extracted).returncode,0)
