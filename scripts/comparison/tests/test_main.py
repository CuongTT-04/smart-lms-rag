import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.comparison.main_entry import no_previous_main, smoke_gate
from scripts.comparison.package_main import ROOT, copy_runtime, main_notebook, probe_entrypoints
from scripts.comparison.package_runner import copy
from scripts.comparison.protocol import write_bundle, write_json
from scripts.comparison.runner import run
from scripts.comparison.tests.test_runner import FakeRuntime, Tokenizer, package
from scripts.qlora.data import sha_file


class SmokeRuntime(FakeRuntime):
    def generate(self, row):
        result, timing = super().generate(row)
        enabled = row['arm'] == 'tuned_rag'
        timing['adapter_state'] = dict(enabled=enabled, layers=196,
            disabled_layers=0 if enabled else 196, merged=False, active_adapter='selected')
        return result, timing


class MainTests(unittest.TestCase):
    def test_exported_entrypoints_run_from_package_without_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            names = ('scripts/comparison/__init__.py', 'scripts/comparison/runner.py',
                     'scripts/comparison/packing.py', 'scripts/comparison/protocol.py',
                     'scripts/comparison/requirements.txt', 'scripts/qlora/__init__.py',
                     'scripts/qlora/data.py', 'scripts/qlora/runtime.py', 'scripts/qlora/requirements.txt')
            for name in names:
                copy(ROOT / name, source / name)
            write_json(source / 'tokenizer-reference.json', {})
            copy(ROOT / 'scripts/comparison/training.py', source / 'scripts/comparison/training.py')
            contents = root / 'contents'
            exported = copy_runtime(source, contents)
            self.assertIn('scripts/comparison/kaggle.py', exported)
            self.assertFalse((contents / 'scripts/comparison/training.py').exists())
            self.assertEqual(len(probe_entrypoints(contents)), 3)

    def test_entrypoint_probe_rejects_missing_kaggle_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'MAIN_PACKAGE_ENTRYPOINT'):
                probe_entrypoints(Path(tmp))

    def smoke(self, root):
        folder = package(root / 'package')
        smoke = root / 'runs/smoke'
        with patch('scripts.comparison.runner.audit_assets', return_value=(Tokenizer(), {})), \
                patch('scripts.comparison.runner.version', return_value='fixture-only'):
            run(folder, smoke, 'smoke', SmokeRuntime)
        return folder, smoke

    def mutate(self, path, change):
        rows = [json.loads(s) for s in path.read_text().splitlines()]
        change(rows)
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))

    def test_bound_successful_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, smoke = self.smoke(Path(tmp))
            self.assertEqual(smoke_gate(folder, smoke)['rows'], 3)

    def test_other_package_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, smoke = self.smoke(Path(tmp))
            write_json(folder / 'manifest.json', {'different': True})
            with self.assertRaisesRegex(ValueError, 'PACKAGE_BINDING'):
                smoke_gate(folder, smoke)

    def test_failed_smoke_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, smoke = self.smoke(Path(tmp))
            self.mutate(smoke / 'outputs.jsonl', lambda rows: rows[0].update(status='timeout', stop_reason='timeout'))
            with self.assertRaisesRegex(ValueError, 'SMOKE_FAILED'):
                smoke_gate(folder, smoke)

    def test_changed_audit_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, smoke = self.smoke(Path(tmp))
            write_json(smoke / 'audit.json', {})
            with self.assertRaisesRegex(ValueError, 'AUDIT_CHANGED'):
                smoke_gate(folder, smoke)

    def test_missing_warmup_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, smoke = self.smoke(Path(tmp))
            self.mutate(smoke / 'warmup.jsonl', lambda rows: rows.pop())
            with self.assertRaisesRegex(ValueError, 'SMOKE_WARMUP'):
                smoke_gate(folder, smoke)

    def test_wrong_lora_state_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, smoke = self.smoke(Path(tmp))
            self.mutate(smoke / 'measurements.jsonl', lambda rows: rows[0]['adapter_state'].update(layers=1))
            with self.assertRaisesRegex(ValueError, 'LORA_STATE'):
                smoke_gate(folder, smoke)

    def test_prior_main_blocks_silent_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder, smoke = self.smoke(root)
            no_previous_main(folder, root / 'runs')
            write_json(root / 'runs/main/run-plan.json', dict(mode='main',
                package_manifest_sha256=sha_file(folder / 'manifest.json')))
            with self.assertRaisesRegex(ValueError, 'MAIN_ALREADY_STARTED'):
                no_previous_main(folder, root / 'runs')

    def test_notebook_four_cells_bound_gate_no_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder, _ = self.smoke(root)
            archive = root / 'runner-main.zip'
            receipt = write_bundle(folder, archive)
            notebook = main_notebook(archive, receipt['zip_sha256'])
            cells = [''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code']
            self.assertEqual(len(cells), 4)
            for source in cells:
                ast.parse(source)
                self.assertNotIn('scripts.comparison.training', source)
            self.assertIn(receipt['zip_sha256'], cells[0])
            self.assertIn('runner-main.zip', cells[0])
            self.assertIn('scripts.comparison.main_entry', cells[2])
            self.assertIn('--smoke-run', cells[2])
            self.assertIn("execute('main')", cells[3])
            self.assertIn("MAIN_AUDIT['rows'] == 900", cells[3])
