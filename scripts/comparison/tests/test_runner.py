from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.comparison.packing import build_messages, pack_contexts, schedule
from scripts.comparison.protocol import canonical, digest, read_rows
from scripts.comparison.runner import (ARMS, LIMITS, MODEL, REVISION, adapter_state,
                                      audit_outputs, run, validate_config, validate_inputs)
from scripts.qlora.runtime import inventory, write_json


class Tokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return list(canonical(messages))

    def encode(self, text, **kwargs):
        return list(text.encode())


def config():
    return dict(model_id=MODEL, model_revision=REVISION, generation=dict(LIMITS),
        attempts=1, warmup_calls_per_arm=2, stage='DEV_ONLY', main_authorized=False,
        adapter_sha256='b'*64,history=False,response_cache=False,repair=False,retries=False)


def assets(count=30):
    inputs, caches, models = [], [], []
    for index in range(count):
        item = dict(qa_id=f'D{index:020x}',question='Question '+str(index),scope_id='00000000-0000-0000-0000-000000000001')
        cache = dict(**item, contexts=[],contexts_sha256=digest([]))
        inputs.append(item)
        caches.append(cache)
        for arm in ARMS:
            messages = build_messages(cache,arm)
            tokens = Tokenizer().apply_chat_template(messages)
            models.append(dict(qa_id=item['qa_id'],arm=arm,messages=messages,input_sha256=digest(messages),
                contexts_sha256=None if arm=='base' else digest([]),input_token_ids_sha256=digest(tokens),input_tokens=len(tokens)))
    return inputs,caches,models


def package(folder):
    folder.mkdir()
    (folder/'inputs').mkdir()
    inputs,caches,models = assets()
    for suffix,rows in [('inputs',inputs),('cache',caches),('model-inputs',models)]:
        (folder/'inputs'/('dev.'+suffix+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    write_json(folder/'inputs/dev.schedule.json',schedule(inputs))
    write_json(folder/'run-config.json',config())
    write_json(folder/'manifest.json',dict(files=inventory(folder)))
    return folder


class FakeRuntime:
    calls = 0
    load_seconds = 0.1

    def __init__(self, package, config):
        type(self).calls = 0

    def generate(self, row):
        type(self).calls += 1
        return dict(raw_output='{"items":[]}',status='completed',stop_reason='eos',output_tokens=4,
                    generation_seconds=0.01,error=None), dict(adapter_state=dict(enabled=row['arm']=='tuned_rag'))


class RunnerPolicyTests(unittest.TestCase):
    def test_dev_config(self):
        validate_config(config(),'dev')

    def test_main_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'MAIN_NOT_FROZEN'):
            validate_config(config(),'main')

    def test_model_revision_locked(self):
        settings=config()
        settings['model_revision']='main'
        with self.assertRaisesRegex(ValueError,'MODEL_PIN'):
            validate_config(settings,'dev')

    def test_no_generation_parameter_drift(self):
        settings=config()
        settings['generation']['max_new_tokens']=256
        with self.assertRaisesRegex(ValueError,'GENERATION_POLICY'):
            validate_config(settings,'dev')

    def test_no_retry_setting(self):
        settings=config()
        settings['attempts']=2
        with self.assertRaisesRegex(ValueError,'ATTEMPTS'):
            validate_config(settings,'dev')

    def test_no_repair_or_response_cache(self):
        settings=config()
        settings['response_cache']=True
        with self.assertRaisesRegex(ValueError,'FEATURE_POLICY'):
            validate_config(settings,'dev')

    def test_frozen_input_tokens(self):
        self.assertEqual(len(validate_inputs(*assets(),Tokenizer())),90)

    def test_gold_field_blocked(self):
        inputs,caches,models=assets()
        inputs[0]['answerable']=True
        with self.assertRaisesRegex(ValueError,'GOLD_OR_UNKNOWN'):
            validate_inputs(inputs,caches,models,Tokenizer())

    def test_changed_question_cannot_use_old_cache(self):
        inputs,caches,models=assets()
        inputs[0]['question']='New question'
        with self.assertRaisesRegex(ValueError,'STALE_CACHE'):
            validate_inputs(inputs,caches,models,Tokenizer())

    def test_context_hash_drift(self):
        inputs,caches,models=assets()
        caches[0]['contexts_sha256']='bad'
        with self.assertRaises(ValueError):
            validate_inputs(inputs,caches,models,Tokenizer())

    def test_token_ids_drift(self):
        inputs,caches,models=assets()
        models[0]['input_token_ids_sha256']='bad'
        with self.assertRaisesRegex(ValueError,'TOKEN_BINDING'):
            validate_inputs(inputs,caches,models,Tokenizer())

    def test_swapped_rag_input(self):
        inputs,caches,models=assets()
        models[2]['messages']=models[0]['messages']
        with self.assertRaisesRegex(ValueError,'PROMPT_BINDING'):
            validate_inputs(inputs,caches,models,Tokenizer())

    def test_missing_arm(self):
        inputs,caches,models=assets()
        with self.assertRaisesRegex(ValueError,'THREE_ARM_COVERAGE'):
            validate_inputs(inputs,caches,models[:-1],Tokenizer())

    def test_duplicate_model_row(self):
        inputs,caches,models=assets()
        with self.assertRaisesRegex(ValueError,'DUPLICATE_MODEL_INPUT'):
            validate_inputs(inputs,caches,models+[models[0]],Tokenizer())

    def test_balanced_schedule(self):
        planned=schedule(assets()[0])
        self.assertEqual(planned,schedule(assets()[0]))
        self.assertEqual(len({tuple(r['arms']) for r in planned}),6)

    def test_question_system_budget(self):
        item=dict(qa_id='D'+'0'*20,question='X'*5000,scope_id='scope',contexts=[])
        with self.assertRaises(ValueError):
            pack_contexts(item,Tokenizer())


class ExecutionTests(unittest.TestCase):
    def execute(self, folder, runtime=FakeRuntime):
        source=package(Path(folder)/'package')
        target=Path(folder)/'run'
        with patch('scripts.comparison.runner.audit_assets',return_value=(Tokenizer(),dict(status='TEST_DOUBLE_NOT_GPU'))), \
             patch('scripts.comparison.runner.version',return_value='TEST_DOUBLE_NOT_GPU'):
            run(source,target,'smoke',runtime)
        return target

    def test_warmup_outside_denominator_and_three_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            target=self.execute(folder)
            self.assertEqual(FakeRuntime.calls,9)
            self.assertEqual(len(read_rows(target/'warmup.jsonl')),6)
            self.assertEqual(len(read_rows(target/'outputs.jsonl')),3)
            self.assertEqual(json.loads((target/'audit.json').read_text())['rows'],3)

    def test_actual_failure_row_is_not_retried(self):
        class Failure(FakeRuntime):
            def generate(self,row):
                result,timing=super().generate(row)
                if type(self).calls==7:
                    result.update(status='model_error',error='test failure',raw_output='partial',stop_reason='exception')
                return result,timing
        with tempfile.TemporaryDirectory() as folder:
            target=self.execute(folder,Failure)
            self.assertEqual(Failure.calls,9)
            rows=read_rows(target/'outputs.jsonl')
            self.assertEqual(rows[0]['raw_output'],'partial')
            self.assertEqual(json.loads((target/'audit.json').read_text())['failure_rows'],1)

    def test_warmup_failure_aborts_assigned_cases(self):
        class Failure(FakeRuntime):
            def generate(self,row):
                result,timing=super().generate(row)
                result.update(status='timeout',stop_reason='timeout')
                return result,timing
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'WARMUP_FAILED'):
                self.execute(folder,Failure)
            self.assertEqual(Failure.calls,1)
            self.assertFalse((Path(folder)/'run/outputs.jsonl').exists())
            self.assertEqual(json.loads((Path(folder)/'run/failure.json').read_text())['persisted_rows'],0)

    def test_existing_output_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            target=self.execute(folder)
            with self.assertRaisesRegex(ValueError,'NEW_DISJOINT'):
                run(Path(folder)/'package',target,'smoke',FakeRuntime)

    def test_output_missing_row(self):
        with tempfile.TemporaryDirectory() as folder:
            target=self.execute(folder)
            expected=assets()[2][:3]
            rows=read_rows(target/'outputs.jsonl')
            with self.assertRaisesRegex(ValueError,'INCOMPLETE'):
                audit_outputs(expected,rows[:-1],'b'*64)

    def test_duplicate_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target=self.execute(folder)
            rows=read_rows(target/'outputs.jsonl')
            with self.assertRaisesRegex(ValueError,'DUPLICATE_OR_UNKNOWN'):
                audit_outputs(assets()[2][:3],rows+[rows[0]],'b'*64)

    def test_wrong_adapter_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target=self.execute(folder)
            rows=read_rows(target/'outputs.jsonl')
            rows[0]['adapter_enabled']=not rows[0]['adapter_enabled']
            with self.assertRaisesRegex(ValueError,'ADAPTER_BINDING'):
                audit_outputs(assets()[2][:3],rows,'b'*64)


class RealPeftStateTests(unittest.TestCase):
    def test_actual_cpu_adapter_disable_enable_not_declarations(self):
        import torch
        from peft import LoraConfig, get_peft_model
        from transformers import GPT2Config, GPT2LMHeadModel
        model=get_peft_model(GPT2LMHeadModel(GPT2Config(n_layer=1,n_head=1,n_embd=8,vocab_size=16)),
            LoraConfig(r=2,lora_alpha=4,target_modules=['c_attn'],task_type='CAUSAL_LM'),adapter_name='selected')
        model.eval()
        torch.manual_seed(42)
        with torch.no_grad():
            for name,value in model.named_parameters():
                if 'lora_B' in name:
                    value.normal_(0,0.5)
        sample=dict(input_ids=torch.tensor([[1,2,3]]),attention_mask=torch.ones(1,3,dtype=torch.long))
        self.assertTrue(adapter_state(model,True)['enabled'])
        with torch.inference_mode():
            tuned=model(**sample).logits
        with model.disable_adapter():
            self.assertFalse(adapter_state(model,False)['enabled'])
            with self.assertRaisesRegex(ValueError,'DISABLE_OR_MERGE'):
                adapter_state(model,True)
            with torch.inference_mode():
                base=model(**sample).logits
        with model.disable_adapter(), torch.inference_mode():
            rag=model(**sample).logits
        self.assertTrue(torch.equal(base,rag))
        self.assertGreater(float((base-tuned).abs().max()),1e-7)
        self.assertTrue(adapter_state(model,True)['enabled'])


if __name__ == '__main__':
    unittest.main()
