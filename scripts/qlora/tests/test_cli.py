from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts.qlora.data import read_json
from scripts.qlora.runtime import verify_inventory
from scripts.qlora.train import main

RECIPE = Path(__file__).resolve().parents[3] / 'configs/qlora-pilot.json'


class CLITests(unittest.TestCase):
    def test_help_does_not_load_model(self):
        with patch('scripts.qlora.train.load_training_model') as load, redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(['--help'])
            self.assertEqual(error.exception.code, 0)
            load.assert_not_called()

    def test_cpu_preflight_never_loads_weights(self):
        row = {'input_ids': [10, 11, 12, 151645], 'attention_mask': [1] * 4,
               'labels': [-100, -100, 12, 151645]}
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'check'
            with patch('scripts.qlora.train.load_pilot', return_value=(
                    {'train': [row], 'validation': [deepcopy(row)]}, object(), {})), \
                 patch('scripts.qlora.train.load_training_model') as load, redirect_stdout(io.StringIO()):
                main(['--config', str(RECIPE), '--bundle', str(Path(root) / 'inputs'),
                      '--profile', 'smoke', '--output', str(output), '--preflight-only'])
                load.assert_not_called()
            report = read_json(output / 'run-manifest.json')
            self.assertEqual(report['status'], 'PREFLIGHT_PASSED')
            verify_inventory(output, report['files'])

    def test_failed_validation_keeps_failed_run_without_model_load(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'failed'
            with patch('scripts.qlora.train.load_pilot', side_effect=ValueError('MANIFEST_HASH')), \
                 patch('scripts.qlora.train.load_training_model') as load:
                with self.assertRaisesRegex(ValueError, 'MANIFEST_HASH'):
                    main(['--config', str(RECIPE), '--bundle', str(Path(root) / 'inputs'),
                          '--profile', 'smoke', '--output', str(output)])
                load.assert_not_called()
            report = read_json(output / 'run-manifest.json')
            self.assertEqual(report['status'], 'FAILED')
            self.assertEqual(report['error_type'], 'ValueError')
            verify_inventory(output, report['files'])

    def test_stop_requires_authenticated_resume(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, 'RESUME_ARGUMENTS_REQUIRED'):
                main(['--config', str(RECIPE), '--bundle', str(Path(root) / 'inputs'),
                      '--profile', 'pilot', '--output', str(Path(root) / 'invalid'), '--stop-after-step', '26'])

    def test_package_contains_only_declared_tools_and_no_private_payload(self):
        from scripts.qlora.package import main as package
        from scripts.qlora.data import sha_file
        import hashlib
        with tempfile.TemporaryDirectory() as root, redirect_stdout(io.StringIO()):
            output = Path(root) / 'delivery'
            package(['--output', str(output)])
            receipt = read_json(output / 'qlora-tools.receipt.json')
            self.assertEqual(sha_file(output / receipt['file']), receipt['sha256'])
            with ZipFile(output / receipt['file']) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), set(receipt['files']))
                for name, sha in receipt['files'].items():
                    self.assertFalse(name.startswith('.private/'))
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), sha)

    def test_kaggle_launcher_rejects_non_kaggle_machine(self):
        from scripts.qlora.kaggle import main as launch
        with patch('scripts.qlora.kaggle.sys.platform', 'win32'), \
             patch('scripts.qlora.kaggle.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'KAGGLE_ONLY'):
                launch(['--bundle', 'input', '--profile', 'smoke', '--output', 'new-run'])
            run.assert_not_called()
