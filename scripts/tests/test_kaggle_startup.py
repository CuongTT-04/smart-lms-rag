import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import ast
import os
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('append_startup', ROOT / 'scripts/append_kaggle_startup.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StartupNotebookTests(unittest.TestCase):
    def test_checkpoint_auto_detection_covers_persisted_output_and_ambiguity(self):
        tree=ast.parse((ROOT/'scripts/kaggle_startup_cell.py').read_text(encoding='utf8'))
        helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_ohayo_find_checkpoint')
        ns={};exec(compile(ast.Module(body=[helper],type_ignores=[]),'checkpoint-probe','exec'),ns)
        find=ns['_ohayo_find_checkpoint']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);inputs=root/'input';working=root/'working'
            inputs.mkdir();working.mkdir()
            with self.assertRaisesRegex(RuntimeError,'Khong tim thay'):find(inputs,working)
            checkpoint=working/'ohayo-model';checkpoint.mkdir();(checkpoint/'checkpoint-manifest.json').write_text('{}')
            self.assertEqual(find(inputs,working),str(checkpoint))
            attached=inputs/'saved-model';attached.mkdir();(attached/'checkpoint-manifest.json').write_text('{}')
            self.assertEqual(find(inputs,working),str(attached))
            second=inputs/'other-model';second.mkdir();(second/'checkpoint-manifest.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'nhieu checkpoint'):find(inputs,working)

    def test_legacy_tunnel_parameters_explicitly_use_tunnels_api(self):
        tree = ast.parse((ROOT / 'scripts/kaggle_startup_cell.py').read_text(encoding='utf-8'))
        assignment = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'ngrok_config' for t in n.targets))
        received = {}
        def config(**kwargs):
            received.update(kwargs)
        ns = {'conf': SimpleNamespace(PyngrokConfig=config), 'ngrok_token': 'private'}
        exec(compile(ast.Module(body=[assignment], type_ignores=[]), 'ngrok-config', 'exec'), ns)
        self.assertEqual(received.get('config_version'), '2',
                         'bind_tls/schemes and inspect must go to /api/tunnels, not /api/endpoints')

    def test_tunnel_error_keeps_codes_but_never_credentials(self):
        tree = ast.parse((ROOT / 'scripts/kaggle_startup_cell.py').read_text(encoding='utf-8'))
        helper = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
                       and n.name == '_ohayo_tunnel_error'), None)
        self.assertIsNotNone(helper, 'Tunnel errors must retain a safe diagnostic')
        ns = {}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), 'helper', 'exec'), ns)
        summarize = ns['_ohayo_tunnel_error']
        text = summarize(RuntimeError('auth failed ERR_NGROK_108 authtoken=PRIVATE'))
        self.assertIn('ERR_NGROK_108', text)
        self.assertNotIn('PRIVATE', text)
        text = summarize(ValueError('unknown field inspect, token PRIVATE'))
        self.assertIn('inspect', text)
        self.assertNotIn('PRIVATE', text)

    def startup_function(self, **state):
        tree = ast.parse((ROOT / 'scripts/kaggle_startup_cell.py').read_text(encoding='utf-8'))
        namespace = dict(state)
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'bootstrap-test', 'exec'), namespace)
        return namespace['_ohayo_start']

    def versions(self, name):
        return {'transformers': '4.57.6', 'bitsandbytes': '0.48.2',
                'accelerate': '1.14.0', 'pyngrok': '9.0.2'}[name]

    @patch('importlib.metadata.version')
    @patch('subprocess.run')
    def test_warm_service_returns_without_reloading_model_or_source(self, run, version):
        import hashlib
        version.side_effect = self.versions
        run.return_value = SimpleNamespace(returncode=0)
        token = 'x' * 40
        service = {'thread_alive': lambda: True, 'url': 'https://example.test', 'ngrok_config': object(),
                   'token_hash': hashlib.sha256(token.encode()).hexdigest()}
        ngrok = SimpleNamespace(get_tunnels=lambda **kw: [SimpleNamespace(public_url=service['url'])])
        with patch.dict(os.environ, {'OHAYO_INFERENCE_TOKEN': token, 'NGROK_AUTHTOKEN': 'private'}), \
             patch.dict('sys.modules', {'pyngrok': SimpleNamespace(ngrok=ngrok, __version__='9.0.2')}):
            self.assertIs(self.startup_function(_ohayo_service=service)(), service)
        self.assertEqual(run.call_count, 1)  # Only subprocess import probe, no pip/model generation.

    @patch('importlib.metadata.version')
    @patch('subprocess.run')
    def test_mixed_kernel_version_stops_before_model_load(self, run, version):
        version.side_effect = self.versions
        with patch.dict('sys.modules', {'transformers': SimpleNamespace(__version__='5.16.1')}):
            with self.assertRaisesRegex(RuntimeError, 'KHONG Factory Reset'):
                self.startup_function()()
        run.assert_not_called()

    def test_append_preserves_all_original_cells_and_backup_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample.ipynb'
            original = b'{"cells": [{"cell_type":"code", "source":["print(1)"], "outputs":[1]}]}'
            path.write_bytes(original)
            module.append(path)
            self.assertEqual(path.with_name('sample.before-startup.ipynb').read_bytes(), original)
            result = json.loads(path.read_bytes())
            self.assertEqual(result['cells'][:1], json.loads(original)['cells'])
            self.assertEqual(len(result['cells']), 3)
            compile(''.join(result['cells'][-1]['source']), 'startup', 'exec')
            with self.assertRaises(ValueError):
                module.append(path)

    def test_standalone_cell_never_runs_evaluation_and_embeds_gateway(self):
        source = module.startup_source()
        self.assertIn('OHAYO_GATEWAY_SOURCE = ', source)
        self.assertIn('from_loaded', source)
        self.assertIn('local_files_only=True', source)
        self.assertIn('checkpoint-manifest.json', source)
        self.assertIn('get_secret(label)', source)
        self.assertIn('inspect=False', source)
        self.assertNotIn('run_rag_evaluation', source)
        self.assertNotIn('SMOKE_CASES', source)
        compile(source, 'startup', 'exec')
