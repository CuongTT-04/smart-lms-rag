import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


class TutoringPatchTests(unittest.TestCase):
    def test_exported_cell_reuses_loaded_providers_and_keeps_the_tunnel(self):
        sys.path.insert(0, str(ROOT / 'backend'))
        spec = importlib.util.spec_from_file_location('tutoring_export', ROOT / 'scripts/export_kaggle_tutoring_patch.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source = module.patch_source()
        namespace = {}
        # Load the exported function without starting a live server on this machine.
        exec(compile(source.rsplit('_ayo_install_tutoring_patch()', 1)[0], 'cell', 'exec'), namespace)
        from apps.ai.providers import ModelConfig
        providers = [SimpleNamespace(config=ModelConfig(device=f'cuda:{i}')) for i in range(2)]
        old = SimpleNamespace(wait_idle=Mock(return_value=True), shutdown=Mock(), server_close=Mock())
        service = dict(server=old, url='https://retained.example')
        secrets = ModuleType('kaggle_secrets')
        secrets.UserSecretsClient = lambda: SimpleNamespace(get_secret=lambda key: 'x' * 40)
        server = SimpleNamespace(service_thread=SimpleNamespace(is_alive=lambda: True))
        gateway = "def start_gateway(pipelines, token, config):\n    return TEST_SERVER\n"
        # Observe construction with real pipeline code; no provider load/generate is called.
        original_exec = exec
        captured = {}
        def observe(code, globals):
            if code == gateway:
                globals['TEST_SERVER'] = server
                original_exec(code, globals)
                start = globals['start_gateway']
                def record(pipelines, token, config):
                    captured['providers'] = [p.provider for p in pipelines]
                    return start(pipelines, token, config)
                globals['start_gateway'] = record
            else:
                original_exec(code, globals)
        import io
        namespace.update(_ohayo_dual_providers=providers, _ohayo_service=service,
                         exec=observe)
        namespace['AYO_TUTORING_SOURCES']['gateway'] = gateway
        responses = [io.BytesIO(b'{"config":{}}'), io.BytesIO(b'{"ready":true,"capabilities":["diagnosed_hint_v1","staged_hint_v1"]}')]
        with patch.dict(sys.modules, {'kaggle_secrets': secrets}), patch('urllib.request.urlopen', side_effect=responses):
            namespace['_ayo_install_tutoring_patch']()
        self.assertEqual(captured['providers'], providers)
        self.assertIs(service['server'], server)
        self.assertEqual(service['url'], 'https://retained.example')
        old.shutdown.assert_called_once()
