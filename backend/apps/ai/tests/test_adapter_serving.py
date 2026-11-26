import contextlib
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from apps.ai.providers import ModelConfig, GenerationError
from apps.ai.providers.adapters import AdapterModelProvider, validate_adapter, check_active_adapter, tokenizer_digest
from apps.ai.providers.local import LocalModelProvider
from apps.ai.inference_gateway import start_gateway


class AdapterServingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = ModelConfig()
        self.weights = b'synthetic adapter fixture; not real safetensors'
        self.digest = hashlib.sha256(self.weights).hexdigest()
        self.adapter = dict(base_model_name_or_path=self.config.model_id, revision=self.config.revision,
                            peft_type='LORA',task_type='CAUSAL_LM',bias='none',r=8,lora_alpha=16)
        self.tokenizer_data = dict(model={'type':'BPE','vocab':{'a':0}},pre_tokenizer={'type':'Sequence'},added_tokens=[])
        self.reference = dict(model_id=self.config.model_id,revision=self.config.revision,
                              eos_token_id=2,pad_token_id=0,chat_template_sha256=hashlib.sha256(b'template').hexdigest(),
                              serving_tokenizer_semantics_sha256=tokenizer_digest(self.tokenizer_data))
        self.write_package()

    def write_package(self):
        directory = self.root/'tokenizer'
        directory.mkdir(exist_ok=True)
        tokenizer_files = {'tokenizer.json':json.dumps(self.tokenizer_data).encode(),
            'config.json':b'{"model_type":"qwen2"}', 'tokenizer_config.json':b'{}',
            'vocab.json':b'{"a":0}', 'merges.txt':b'#version: 0.2\n'}
        for name,data in tokenizer_files.items():
            (directory/name).write_bytes(data)
        self.reference['files'] = {name:dict(sha256=hashlib.sha256(data).hexdigest(),size_bytes=len(data))
                                   for name,data in tokenizer_files.items()}
        (self.root/'adapter_config.json').write_text(json.dumps(self.adapter))
        (self.root/'adapter_model.safetensors').write_bytes(self.weights)
        (self.root/'tokenizer-reference.json').write_text(json.dumps(self.reference))
        files = {p.relative_to(self.root).as_posix():dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),size_bytes=p.stat().st_size)
                 for p in self.root.rglob('*') if p.is_file() and p.name!='serving-manifest.json'}
        (self.root/'serving-manifest.json').write_text(json.dumps(dict(schema_version=1,
            model=self.config.model_id,revision=self.config.revision,files=files)))

    def test_valid_package(self):
        manifest, reference = validate_adapter(self.root,self.digest,self.config)
        self.assertEqual(manifest['revision'],self.config.revision)
        self.assertEqual(reference['eos_token_id'],2)

    def test_modified_weights_fail(self):
        (self.root/'adapter_model.safetensors').write_bytes(b'corrupted')
        with self.assertRaises(GenerationError):
            validate_adapter(self.root,self.digest,self.config)

    def test_other_candidate_fails_even_with_valid_manifest(self):
        with self.assertRaises(GenerationError):
            validate_adapter(self.root,'0'*64,self.config)

    def test_wrong_base_revision_fails(self):
        self.adapter['revision'] = '0'*40
        self.write_package()
        with self.assertRaises(GenerationError):
            validate_adapter(self.root,self.digest,self.config)

    def test_pickle_or_training_files_rejected(self):
        (self.root/'training_args.bin').write_bytes(b'pickle is not an inference input')
        with self.assertRaises(GenerationError):
            validate_adapter(self.root,self.digest,self.config)

    def test_modules_to_save_rejected(self):
        self.adapter['modules_to_save'] = ['embed_tokens']
        self.write_package()
        with self.assertRaises(GenerationError):
            validate_adapter(self.root,self.digest,self.config)

    def test_tokenizer_serialization_not_semantics(self):
        data = dict(self.tokenizer_data,padding=None,truncation=None)
        self.assertEqual(tokenizer_digest(data),tokenizer_digest(self.tokenizer_data))
        data['model'] = {'type':'BPE','vocab':{'b':0}}
        self.assertNotEqual(tokenizer_digest(data),tokenizer_digest(self.tokenizer_data))

    def test_bad_adapter_fails_before_model_loading(self):
        provider = AdapterModelProvider(self.config,adapter_path=self.root,adapter_sha256='0'*64)
        with patch.object(LocalModelProvider,'_build_runtime') as base:
            with self.assertRaises(GenerationError):
                provider._build_runtime()
            base.assert_not_called()

    def fake_loaded_runtime(self):
        base = MagicMock()
        base.config = SimpleNamespace(vocab_size=4)
        model = MagicMock()
        parameter = MagicMock()
        model.parameters.return_value = [parameter]
        tokenizer = SimpleNamespace(eos_token_id=2,pad_token_id=0,chat_template='template',
            get_vocab=lambda:{'a':0},
            backend_tokenizer=SimpleNamespace(to_str=lambda:json.dumps(self.tokenizer_data)))
        tensor = MagicMock()
        tensor.shape = (1,)
        tensor.detach.return_value.cpu.return_value = tensor
        torch = SimpleNamespace(equal=MagicMock(return_value=True))
        peft = SimpleNamespace(PeftModel=SimpleNamespace(from_pretrained=MagicMock(return_value=model)),
                               get_peft_model_state_dict=MagicMock(return_value={'weight':tensor}))
        safe = SimpleNamespace(load_file=MagicMock(return_value={'weight':tensor}))
        return base,model,tokenizer,torch,peft,safe,parameter

    def test_load_verifies_actual_tensor_values_and_freezes_parameters(self):
        base,model,tokenizer,torch,peft,safe,parameter = self.fake_loaded_runtime()
        provider = AdapterModelProvider(self.config,adapter_path=self.root,adapter_sha256=self.digest)
        with patch.object(LocalModelProvider,'_build_runtime',return_value=(base,tokenizer,torch)), \
             patch.dict(sys.modules,{'peft':peft,'safetensors.torch':safe}), \
             patch('apps.ai.providers.adapters.check_active_adapter',return_value=1), \
             patch.object(provider,'_check_runtime'):
            actual = provider._build_runtime()
        self.assertIs(actual[0],model)
        parameter.requires_grad_.assert_called_once_with(False)
        self.assertTrue(provider.adapter_audit['tensor_values_match'])
        self.assertFalse(peft.PeftModel.from_pretrained.call_args.kwargs['is_trainable'])
        self.assertTrue(peft.PeftModel.from_pretrained.call_args.kwargs['local_files_only'])
        self.assertEqual(provider.adapter_audit['trainable_parameters'],0)

    def test_loaded_tensor_mismatch_fails_closed(self):
        base,model,tokenizer,torch,peft,safe,_ = self.fake_loaded_runtime()
        torch.equal.return_value = False
        provider = AdapterModelProvider(self.config,adapter_path=self.root,adapter_sha256=self.digest)
        with patch.object(LocalModelProvider,'_build_runtime',return_value=(base,tokenizer,torch)), \
             patch.dict(sys.modules,{'peft':peft,'safetensors.torch':safe}):
            with self.assertRaises(GenerationError) as caught:
                provider._build_runtime()
        self.assertEqual(caught.exception.code,'ADAPTER_LOAD_FAILED')
        self.assertIsNone(provider.adapter_audit)

    def test_wrong_tokenizer_stops_before_peft(self):
        base,model,tokenizer,torch,peft,safe,_ = self.fake_loaded_runtime()
        tokenizer.eos_token_id = 99
        provider = AdapterModelProvider(self.config,adapter_path=self.root,adapter_sha256=self.digest)
        with patch.object(LocalModelProvider,'_build_runtime',return_value=(base,tokenizer,torch)), \
             patch.dict(sys.modules,{'peft':peft,'safetensors.torch':safe}):
            with self.assertRaises(GenerationError) as caught:
                provider._build_runtime()
        self.assertEqual(caught.exception.code,'ADAPTER_TOKENIZER_MISMATCH')
        peft.PeftModel.from_pretrained.assert_not_called()

    def test_disabled_or_merged_adapter_is_rejected(self):
        class LoraLayer:
            disable_adapters = False
            merged_adapters = []
            active_adapters = ['default']
        layer = LoraLayer()
        model = SimpleNamespace(active_adapters=['default'],modules=lambda:[layer])
        with patch.dict(sys.modules,{'peft.tuners.lora':SimpleNamespace(LoraLayer=LoraLayer)}):
            self.assertEqual(check_active_adapter(model),1)
            layer.disable_adapters = True
            with self.assertRaises(GenerationError):
                check_active_adapter(model)
            layer.disable_adapters = False
            layer.merged_adapters = ['default']
            with self.assertRaises(GenerationError):
                check_active_adapter(model)

    def test_identity_unavailable_before_loading(self):
        provider = AdapterModelProvider(self.config,adapter_path=self.root,adapter_sha256=self.digest)
        with self.assertRaises(GenerationError):
            provider.serving_identity()

    def test_tokenizer_is_loaded_from_training_assets_not_old_checkpoint(self):
        _,_,tokenizer,_,_,_,_ = self.fake_loaded_runtime()
        loader = SimpleNamespace(from_pretrained=MagicMock(return_value=tokenizer))
        provider = AdapterModelProvider(self.config,adapter_path=self.root,adapter_sha256=self.digest)
        actual = provider._load_tokenizer(loader, '/old-nf4-checkpoint', {'revision':'old'})
        self.assertIs(actual,tokenizer)
        loader.from_pretrained.assert_called_once_with(str(self.root/'tokenizer'),
            local_files_only=True,trust_remote_code=False,fix_mistral_regex=False)
        self.assertEqual(provider.tokenizer_audit['source'],'verified_adapter_training_tokenizer')

    def test_corrupted_training_tokenizer_fails_before_loading(self):
        (self.root/'tokenizer/vocab.json').write_bytes(b'changed')
        provider = AdapterModelProvider(self.config,adapter_path=self.root,adapter_sha256=self.digest)
        loader = MagicMock()
        with self.assertRaises(GenerationError):
            provider._load_tokenizer(loader, '/old-nf4-checkpoint', {})
        loader.from_pretrained.assert_not_called()

    def test_training_tokenizer_ids_must_fit_model_embeddings(self):
        base,model,tokenizer,torch,peft,safe,_ = self.fake_loaded_runtime()
        base.config.vocab_size = 2
        provider = AdapterModelProvider(self.config,adapter_path=self.root,adapter_sha256=self.digest)
        with patch.object(LocalModelProvider,'_build_runtime',return_value=(base,tokenizer,torch)):
            with self.assertRaises(GenerationError) as caught:
                provider._build_runtime()
        self.assertEqual(caught.exception.code,'ADAPTER_TOKENIZER_MISMATCH')

    def test_old_checkpoint_tokenizer_is_not_required_to_match_training_export(self):
        from dataclasses import replace
        old = self.root/'old-checkpoint'
        old.mkdir()
        (old/'tokenizer.json').write_text('{"pre_tokenizer":"old export"}')
        config = replace(self.config,checkpoint_path=str(old))
        base,model,tokenizer,torch,peft,safe,_ = self.fake_loaded_runtime()
        provider = AdapterModelProvider(config,adapter_path=self.root,adapter_sha256=self.digest)
        # The checkpoint directory is a different input, not part of adapter inventory.
        provider.adapter_path = str(self.root/'package')
        (self.root/'package').mkdir()
        for path in list(self.root.iterdir()):
            if path.name not in ('old-checkpoint','package'):
                path.rename(self.root/'package'/path.name)
        with patch.object(LocalModelProvider,'_build_runtime',return_value=(base,tokenizer,torch)), \
             patch.dict(sys.modules,{'peft':peft,'safetensors.torch':safe}), \
             patch('apps.ai.providers.adapters.check_active_adapter',return_value=1), \
             patch.object(provider,'_check_runtime'):
            self.assertIs(provider._build_runtime()[0],model)


class GatewayIdentityTests(unittest.TestCase):
    def server(self, identity):
        server = start_gateway(SimpleNamespace(generate_answer=lambda **kw:None), 'x'*40,
                               {'model':'Qwen'},port=0,identity_provider=identity)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}/health'

    def test_health_reports_identity_without_changing_generation_config(self):
        url = self.server(lambda:dict(arm='tuned_rag',adapter_sha256='a'*64))
        with urlopen(Request(url,headers={'Authorization':'Bearer '+'x'*40})) as response:
            health = json.load(response)
        self.assertEqual(health['serving']['arm'],'tuned_rag')
        self.assertEqual(health['config'],{'model':'Qwen'})

    def test_invalid_identity_is_not_ready_and_does_not_leak_exception(self):
        def fail():
            raise RuntimeError('private internal detail')
        url = self.server(fail)
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(url,headers={'Authorization':'Bearer '+'x'*40}))
        self.assertEqual(caught.exception.code,503)
        body = caught.exception.read()
        self.assertNotIn(b'private',body)
        self.assertFalse(json.loads(body)['ready'])


if __name__ == '__main__':
    unittest.main()
