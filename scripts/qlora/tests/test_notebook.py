import hashlib
import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from scripts.qlora.data import read_json

ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless((ROOT / 'notebooks/qlora_training.ipynb').is_file(),
                     'Notebook is a repository artifact, not part of the compact tools ZIP')
class NotebookTests(unittest.TestCase):
    def test_notebook_environment_source_matches_reviewed_module(self):
        notebook = read_json(ROOT / 'notebooks/qlora_training.ipynb')
        source = (ROOT / 'scripts/qlora/setup.py').read_text(encoding='utf-8').encode('utf-8')
        self.assertEqual(notebook['metadata']['ohayo_environment_overlay']['sha256'],
                         hashlib.sha256(source).hexdigest())
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code':
                compile(''.join(cell['source']), 'notebook-cell', 'exec')

    def test_overlay_preserves_locked_input_and_is_repeatable(self):
        notebook = read_json(ROOT / 'notebooks/qlora_training.ipynb')
        code = ''.join(notebook['cells'][2]['source'])
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            original = root / 'tools/scripts/qlora'
            original.mkdir(parents=True)
            (original / 'setup.py').write_bytes(b'# locked original\n')
            (original / 'data.py').write_bytes(b'# locked helper\n')
            namespace = dict(WORK=root, HANDOFF=root / 'handoff', Path=Path, sys=sys)
            with patch('subprocess.run') as run:
                exec(compile(code, 'notebook-cell', 'exec'), namespace)
                exec(compile(code, 'notebook-cell-rerun', 'exec'), namespace)
            self.assertEqual((original / 'setup.py').read_bytes(), b'# locked original\n')
            self.assertEqual((namespace['TOOLS'] / 'scripts/qlora/data.py').read_bytes(), b'# locked helper\n')
            self.assertIn('--environment-only', run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs['env']['CUDA_VISIBLE_DEVICES'], '0')
            self.assertNotIn('--allow-model-download', run.call_args.args[0])
            self.assertEqual(run.call_count, 6)
            (namespace['TOOLS'] / 'scripts/qlora/setup.py').write_bytes(b'# modified\n')
            with patch('subprocess.run'), self.assertRaises(AssertionError):
                exec(compile(code, 'notebook-cell-corrupted', 'exec'), namespace)

    def smoke_cell(self):
        notebook = read_json(ROOT / 'notebooks/qlora_training.ipynb')
        return notebook, ''.join(next(c for c in notebook['cells'] if c.get('id') == 'gpu-smoke')['source'])

    def test_smoke_sources_match_repo_and_profile_is_exactly_smoke(self):
        notebook, code = self.smoke_cell()
        tree = ast.parse(code)
        sources = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id == 'SMOKE_SOURCES':
                    sources = ast.literal_eval(node.value)
                elif node.targets[0].id == 'command':
                    constants = [n.value for n in node.value.elts if isinstance(n, ast.Constant)]
                    self.assertEqual(constants[constants.index('--profile') + 1], 'smoke')
                    self.assertIn('--cache-dir', constants)
        self.assertIsNotNone(sources)
        for name, content in sources.items():
            self.assertEqual(content, (ROOT / 'scripts/qlora' / name).read_text(encoding='utf-8'))
        sha = hashlib.sha256(json.dumps(sources, ensure_ascii=False, sort_keys=True,
                                       separators=(',', ':')).encode('utf-8')).hexdigest()
        self.assertEqual(sha, notebook['metadata']['ohayo_gpu_smoke']['source_id'])
        self.assertEqual(notebook['metadata']['ohayo_gpu_smoke']['max_steps'], 2)

    def test_smoke_notebook_creates_separate_runtime_and_never_launches_pilot(self):
        _, code = self.smoke_cell()
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            base = root / 'tools-environment'
            (base / 'scripts/qlora').mkdir(parents=True)
            (base / 'scripts/qlora/setup.py').write_bytes(b'# approved setup\n')
            report = root / 'report'
            report.mkdir()
            (report / 'environment-check.json').write_text('{"status":"ENVIRONMENT_READY_FOR_SMOKE"}', encoding='utf-8')
            import datetime, hashlib, json, shutil, subprocess
            namespace = dict(WORK=root, RUN_TOOLS=base, REPORT=report, HANDOFF=root / 'handoff',
                Path=Path, sys=sys, hashlib=hashlib, json=json, shutil=shutil, subprocess=subprocess,
                VENV=root / 'venv', datetime=datetime.datetime, timezone=datetime.timezone)
            process = SimpleNamespace(poll=lambda: 0, returncode=0)
            with patch('subprocess.Popen', return_value=process) as spawn, redirect_stdout(io.StringIO()):
                exec(compile(code, 'smoke-cell', 'exec'), namespace)
            command = spawn.call_args.args[0]
            self.assertEqual(command[command.index('--profile') + 1], 'smoke')
            self.assertEqual(spawn.call_args.kwargs['env']['CUDA_VISIBLE_DEVICES'], '0')
            self.assertEqual((base / 'scripts/qlora/setup.py').read_bytes(), b'# approved setup\n')
            self.assertNotEqual(namespace['SMOKE_TOOLS'], base)
            self.assertTrue((namespace['SMOKE_TOOLS'] / 'scripts/qlora/storage.py').is_file())
            namespace['SMOKE_PROCESS'] = SimpleNamespace(poll=lambda: None)
            with patch('subprocess.Popen') as spawn, self.assertRaisesRegex(RuntimeError, 'already running'):
                exec(compile(code, 'smoke-cell-duplicate', 'exec'), namespace)
            spawn.assert_not_called()
