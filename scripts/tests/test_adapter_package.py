import json
import contextlib
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts.package_adapter_serving import CELL_INPUT, CELL_START, CELL_VERIFY, CELL_EXPORT, ROOT


class AdapterNotebookTests(unittest.TestCase):
    def test_cells_compile(self):
        code = CELL_INPUT.replace('__PACKAGE_HASH__',repr('a'*64)).replace('__ADAPTER_HASH__',repr('b'*64))
        code = code.replace('__MANIFEST_HASH__',repr('c'*64))
        for source in (code,CELL_START,CELL_VERIFY,CELL_EXPORT):
            compile(source,'cell','exec')

    def test_no_training_or_backend_reconfiguration(self):
        source = CELL_INPUT+CELL_START+CELL_VERIFY+CELL_EXPORT
        for forbidden in ('Trainer(', '.train(', 'AI_INFERENCE_URL=', 'update_env(', 'torch.save('):
            self.assertNotIn(forbidden,source)
        self.assertIn('Run cell 4 even if smoke failed',source)

    def test_profile_binds_arm_and_adapter_to_service_signature(self):
        source = (ROOT/'scripts/kaggle_adapter_cell.py').read_text(encoding='utf-8')
        compile(source,'profile','exec')
        self.assertIn('OHAYO_DUAL_SIGNATURE +=',source)
        self.assertIn('EXPECTED_ADAPTER_SHA256',source)
        self.assertIn('peft_config',source)

    def test_input_is_hash_pinned_and_extraction_bounded(self):
        self.assertIn('== EXPECTED_PACKAGE_SHA256',CELL_INPUT)
        self.assertIn('160 * 1024**2',CELL_INPUT)
        self.assertIn('Unsafe extraction destination',CELL_INPUT)

    def test_smoke_requires_actual_lora_and_no_trainable_parameters(self):
        self.assertIn("replica['loaded_adapter_tensors'] == 392",CELL_VERIFY)
        self.assertIn("replica['trainable_parameters'] == 0",CELL_VERIFY)
        self.assertIn("replica['active_adapter'] == 'default'",CELL_VERIFY)

    def test_kaggle_auto_extracted_input_is_also_verified(self):
        self.assertIn('EXPECTED_MANIFEST_SHA256',CELL_INPUT)
        self.assertIn('Unsafe extracted Input path',CELL_INPUT)

    def test_input_cell_accepts_zip_and_expanded_files(self):
        for expanded in (False,True):
            with self.subTest(expanded=expanded), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                inputs = root/'input'
                inputs.mkdir()
                data = b'pass\n'
                manifest = json.dumps(dict(files={'startup.py':dict(
                    sha256=hashlib.sha256(data).hexdigest(),size_bytes=len(data))})).encode()
                archive_path = root/'serving-input.zip'
                with ZipFile(archive_path,'w') as archive:
                    archive.writestr('manifest.json',manifest)
                    archive.writestr('startup.py',data)
                package_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
                if expanded:
                    (inputs/'manifest.json').write_bytes(manifest)
                    (inputs/'startup.py').write_bytes(data)
                else:
                    (inputs/'serving-input.zip').write_bytes(archive_path.read_bytes())
                code = CELL_INPUT.replace('__PACKAGE_HASH__',repr(package_hash))
                code = code.replace('__MANIFEST_HASH__',repr(hashlib.sha256(manifest).hexdigest()))
                code = code.replace('__ADAPTER_HASH__',repr('a'*64))
                code = code.replace("Path('/kaggle/input')",f'Path({str(inputs)!r})')
                code = code.replace("Path('/kaggle/working/ayo-serving-' + EXPECTED_PACKAGE_SHA256[:12])",
                                    f'Path({str(root/"working")!r})')
                with patch.dict('os.environ'),contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(code,'input-cell','exec'),{})
                self.assertEqual((root/'working/startup.py').read_bytes(),data)


if __name__ == '__main__':
    unittest.main()
