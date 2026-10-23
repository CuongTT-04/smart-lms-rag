import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]


class ConfigureKaggleTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('configure_kaggle',ROOT/'scripts/configure_kaggle_inference.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def run_config(self, replicas):
        module=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            env=root/'.env';env.write_text('AI_INFERENCE_TOKEN='+'x'*40+'\nKEEP_ME=yes\n')
            before=env.read_bytes()
            config=json.loads((ROOT/'backend/config/ai/kaggle-dual-gpu.json').read_text())
            response=io.BytesIO(json.dumps({'ready':True,'replicas':replicas,'config':config}).encode())
            output=io.StringIO()
            with patch.object(module,'ROOT',root), patch.object(module,'build_opener',return_value=SimpleNamespace(open=lambda *a,**kw:response)), \
                    patch('sys.argv',['configure','--url','https://example.test','--dual-gpu','--use-env-token']),contextlib.redirect_stdout(output):
                status=module.main()
            self.assertNotIn('x'*40,output.getvalue())
            return status,env.read_bytes(),before,(root/'backend/config/ai/kaggle-dual-gpu.json').exists()

    def test_docker_uses_the_verified_dual_profile_file(self):
        status,env,_,exists=self.run_config(2)
        env=env.decode()
        self.assertEqual(status,0)
        self.assertTrue(exists)
        self.assertIn('AI_GENERATION_CONFIG=/app/backend/config/ai/kaggle-dual-gpu.json',env)
        self.assertIn('KEEP_ME=yes',env)

    def test_one_replica_does_not_change_env_or_write_dual_config(self):
        status,env,before,exists=self.run_config(1)
        self.assertEqual(status,1)
        self.assertEqual(env,before)
        self.assertFalse(exists)
