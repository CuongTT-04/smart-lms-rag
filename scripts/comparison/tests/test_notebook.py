import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts.comparison.package_runner import make_notebook


class NotebookTests(unittest.TestCase):
    def fixture(self, folder, *, unsafe=False):
        folder=Path(folder)
        source=folder/'input'
        source.mkdir()
        archive=source/'runner-dev.zip'
        files={'safe/file.txt':b'bytes'} if not unsafe else {'../outside.txt':b'unsafe'}
        manifest={n:dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()) for n,raw in files.items()}
        with ZipFile(archive,'x') as zipped:
            for n,raw in files.items():
                zipped.writestr(n,raw)
            zipped.writestr('bundle-manifest.json',json.dumps(manifest))
        notebook=folder/'notebook.ipynb'
        make_notebook(notebook,archive,hashlib.sha256(archive.read_bytes()).hexdigest())
        content=json.loads(notebook.read_text(encoding='utf-8'))
        cells=[''.join(c['source']) for c in content['cells'] if c['cell_type']=='code']
        for code in cells:
            ast.parse(code)
        bootstrap=cells[0].replace('/kaggle/input',source.as_posix()).replace('/kaggle/working',(folder/'working').as_posix())
        return archive,cells,bootstrap

    def execute(self,bootstrap):
        scope={}
        with patch.dict(os.environ,clear=False):
            exec(compile(bootstrap,'notebook-bootstrap','exec'),scope)
        return scope['PACKAGE']

    def test_four_code_cells_compile(self):
        with tempfile.TemporaryDirectory() as folder:
            _,cells,_=self.fixture(folder)
            self.assertEqual(len(cells),4)
            self.assertIn('SMOKE_AUDIT',cells[-1])

    def test_zip_input(self):
        with tempfile.TemporaryDirectory() as folder:
            _,_,bootstrap=self.fixture(folder)
            package=self.execute(bootstrap)
            self.assertEqual((package/'safe/file.txt').read_bytes(),b'bytes')
            self.assertFalse((package/'bundle-manifest.json').exists())

    def test_extracted_kaggle_input(self):
        with tempfile.TemporaryDirectory() as folder:
            archive,_,bootstrap=self.fixture(folder)
            with ZipFile(archive) as zipped:
                zipped.extractall(archive.parent/'dataset')
            archive.unlink()
            package=self.execute(bootstrap)
            self.assertEqual((package/'safe/file.txt').read_bytes(),b'bytes')

    def test_extracted_file_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            archive,_,bootstrap=self.fixture(folder)
            with ZipFile(archive) as zipped:
                zipped.extractall(archive.parent/'dataset')
            archive.unlink()
            (archive.parent/'dataset/safe/file.txt').write_bytes(b'changed')
            with self.assertRaises(AssertionError):
                self.execute(bootstrap)

    def test_idempotent_matching_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            _,_,bootstrap=self.fixture(folder)
            first=self.execute(bootstrap)
            self.assertEqual(first,self.execute(bootstrap))

    def test_existing_changed_file_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            _,_,bootstrap=self.fixture(folder)
            package=self.execute(bootstrap)
            (package/'safe/file.txt').write_bytes(b'changed')
            with self.assertRaises(AssertionError):
                self.execute(bootstrap)
            self.assertEqual((package/'safe/file.txt').read_bytes(),b'changed')

    def test_path_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            _,_,bootstrap=self.fixture(folder,unsafe=True)
            with self.assertRaises(AssertionError):
                self.execute(bootstrap)
            self.assertFalse((Path(folder)/'working/outside.txt').exists())

    def test_unknown_input_files_not_copied(self):
        with tempfile.TemporaryDirectory() as folder:
            archive,_,bootstrap=self.fixture(folder)
            with ZipFile(archive) as zipped:
                zipped.extractall(archive.parent/'dataset')
            archive.unlink()
            (archive.parent/'dataset/main.references.jsonl').write_text('unrelated private data')
            package=self.execute(bootstrap)
            self.assertFalse((package/'main.references.jsonl').exists())


if __name__=='__main__':
    unittest.main()
