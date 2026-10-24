import ast
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]


class DualStartupTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('dual_append',ROOT/'scripts/append_kaggle_dual_gpu.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def helpers(self):
        tree=ast.parse((ROOT/'scripts/kaggle_dual_gpu_cell.py').read_text(encoding='utf8'))
        namespace={}
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef)],type_ignores=[]),'dual-helper','exec'),namespace)
        return namespace

    def test_append_preserves_every_existing_cell_and_embeds_verified_source(self):
        module=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'notebook.ipynb'
            original={'cells':[{'id':'old-startup','cell_type':'code','source':['old()'],'execution_count':2,'outputs':[{'text':'evidence'}]}]}
            path.write_text(json.dumps(original))
            module.append(path)
            result=json.loads(path.read_text())
            self.assertEqual(result['cells'][:-2],original['cells'])
            self.assertEqual(result['cells'][-1]['id'],'ohayo-dual-gpu-startup')
            compile(''.join(result['cells'][-1]['source']),'dual-cell','exec')
            with self.assertRaises(ValueError):module.append(path)

    def test_creates_exactly_one_provider_per_device_and_reuses_loaded_replicas(self):
        sys.path.insert(0,str(ROOT/'backend'))
        from apps.ai.providers import ModelConfig
        namespace=self.helpers()
        loaded=[]
        class Provider:
            def __init__(self,config):self.config=config;self.loaded=False
            def count_tokens(self,messages):
                if not self.loaded:loaded.append(self.config.device);self.loaded=True
                return 4
        torch=SimpleNamespace(set_num_threads=lambda n:None,set_num_interop_threads=lambda n:None,
            cuda=SimpleNamespace(device_count=lambda:2))
        def pipeline(provider,config):return SimpleNamespace(provider=provider,config=config)
        with patch.dict('os.environ',{'OHAYO_CHECKPOINT':'/attached/model'}):
            for _ in range(2):
                pipelines,config=namespace['_ohayo_dual_runtime'](torch,Provider,ModelConfig,pipeline,lambda **kwargs:kwargs,Path('/input'))
                self.assertEqual([p.provider.config.device for p in pipelines],['cuda:0','cuda:1'])
                self.assertEqual(config.max_new_tokens,1024)
                self.assertGreaterEqual(config.context_tokens,config.max_input_tokens+config.max_new_tokens)
                self.assertEqual(config.timeout_seconds,90)
        self.assertEqual(loaded,['cuda:0','cuda:1'])

    def test_requires_two_gpus_without_allocating_a_model(self):
        namespace=self.helpers()
        torch=SimpleNamespace(cuda=SimpleNamespace(device_count=lambda:1))
        with self.assertRaisesRegex(RuntimeError,'T4 x2'):
            namespace['_ohayo_dual_runtime'](torch,None,None,None,None,Path('/input'))

    def test_duplicate_checkpoint_mounts_are_deduplicated_but_different_models_require_selection(self):
        find=self.helpers()['_ohayo_dual_checkpoint']
        with tempfile.TemporaryDirectory() as tmp:
            inputs=Path(tmp)/'input';working=Path(tmp)/'working';working.mkdir()
            paths=[inputs/'notebooks'/'model',inputs/'datasets'/'model']
            for path in paths:
                path.mkdir(parents=True)
                (path/'checkpoint-manifest.json').write_text(json.dumps({'model_id':'Qwen/Qwen2.5-7B-Instruct','files':{'a':'same'}}))
            self.assertEqual(Path(find(inputs,working)),paths[1])
            (paths[0]/'checkpoint-manifest.json').write_text(json.dumps({'model_id':'Qwen/Qwen2.5-7B-Instruct','files':{'a':'different'}}))
            with self.assertRaisesRegex(RuntimeError,'OHAYO_CHECKPOINT'):find(inputs,working)
