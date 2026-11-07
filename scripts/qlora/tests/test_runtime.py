from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch
from peft import LoraConfig, get_peft_model
from transformers import Qwen2Config, Qwen2ForCausalLM, set_seed

from scripts.qlora.collator import CompletionCollator
from scripts.qlora.data import digest, read_json, sha_file
from scripts.qlora.runtime import (adapter_parameters, finish_manifest, fit, inventory,
    load_training_model, make_callbacks, output_guard, resume_checkpoint, training_arguments,
    validate_recipe, verify_inventory, write_json)

RECIPE = Path(__file__).resolve().parents[3] / 'configs/qlora-pilot.json'


def tiny_base():
    set_seed(42)
    model = Qwen2ForCausalLM(Qwen2Config(vocab_size=32, hidden_size=16,
        intermediate_size=32, num_hidden_layers=1, num_attention_heads=2,
        num_key_value_heads=2, max_position_embeddings=64, eos_token_id=2, pad_token_id=0,
        attention_dropout=0.0))
    model.config.use_cache = False
    return model


def tiny_model():
    model = tiny_base()
    model.requires_grad_(False)
    return get_peft_model(model, LoraConfig(r=2, lora_alpha=4, target_modules='all-linear',
                                          task_type='CAUSAL_LM', lora_dropout=0))


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.config = read_json(RECIPE)

    def test_profiles_and_recipe(self):
        for profile, steps, save in (('smoke', 2, 2), ('pilot', 50, 25)):
            validate_recipe(self.config, profile)
            args = training_arguments(self.config, profile, 'unused', cpu_test=True)
            self.assertEqual((args.max_steps, args.save_steps), (steps, save))
            self.assertFalse(args.save_only_model)
            self.assertFalse(args.load_best_model_at_end)
            self.assertEqual(args.gradient_accumulation_steps, 4)

    def test_corrupted_recipe_rejected(self):
        for group, key, value in (('profiles', 'pilot', {'max_steps': 1}),
                                  ('lora', 'r', 16), ('training', 'learning_rate', float('nan'))):
            config = deepcopy(self.config)
            config[group][key] = value
            with self.assertRaises(ValueError):
                validate_recipe(config, 'pilot')

    def test_output_cannot_overlap_inputs_or_existing_run(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, 'OUTPUT_ALREADY_EXISTS'):
                output_guard(root, [])
            with self.assertRaisesRegex(ValueError, 'OUTPUT_OVERLAPS_INPUT'):
                output_guard(Path(root) / 'new', [root])

    def test_inventory_detects_changed_or_traversing_file(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            write_json(folder / 'item.json', {'value': 1})
            entries = inventory(folder)
            verify_inventory(folder, entries)
            write_json(folder / 'item.json', {'value': 2})
            with self.assertRaisesRegex(ValueError, 'ARTIFACT_INTEGRITY'):
                verify_inventory(folder, entries)
            with self.assertRaises(ValueError):
                verify_inventory(folder, {'../outside': {'size_bytes': 0, 'sha256': ''}})

    def test_base_trainability_rejected(self):
        model = tiny_model()
        self.assertTrue(adapter_parameters(model))
        model.get_input_embeddings().weight.requires_grad_(True)
        with self.assertRaisesRegex(ValueError, 'BASE_PARAMETER_TRAINABLE'):
            adapter_parameters(model)

    def test_no_gpu_never_attempts_model_download(self):
        with patch('torch.cuda.is_available', return_value=False), \
             patch('transformers.AutoModelForCausalLM.from_pretrained') as loader:
            # CUDA guard must run before optional bitsandbytes loading/version validation.
            with self.assertRaisesRegex(ValueError, 'CUDA_REQUIRED'):
                load_training_model(self.config)
            loader.assert_not_called()

    def test_gpu_loader_recipe_wiring_without_gpu_execution(self):
        prepared = tiny_model()
        base = SimpleNamespace(config=SimpleNamespace(_commit_hash=self.config['revision'],
                                                      use_cache=True), is_loaded_in_4bit=True)
        with patch('torch.cuda.is_available', return_value=True), \
             patch('torch.cuda.device_count', return_value=1), \
             patch('torch.cuda.get_device_name', return_value='Tesla T4'), \
             patch('torch.cuda.mem_get_info', return_value=(15 * 1024 ** 3, 16 * 1024 ** 3)), \
             patch('torch.distributed.is_initialized', return_value=False), \
             patch('scripts.qlora.runtime.version', side_effect=self.config['dependencies'].__getitem__), \
             patch('transformers.BitsAndBytesConfig') as quantization, \
             patch('transformers.AutoModelForCausalLM.from_pretrained', return_value=base) as loader, \
             patch('peft.prepare_model_for_kbit_training', return_value=base) as prepare, \
             patch('peft.get_peft_model', return_value=prepared):
            self.assertIs(load_training_model(self.config), prepared)
            self.assertEqual(loader.call_args.kwargs['revision'], self.config['revision'])
            self.assertEqual(loader.call_args.kwargs['device_map'], {'': 0})
            self.assertTrue(loader.call_args.kwargs['local_files_only'])
            self.assertFalse(base.config.use_cache)
            self.assertEqual(quantization.call_args.kwargs['bnb_4bit_quant_type'], 'nf4')
            self.assertTrue(quantization.call_args.kwargs['bnb_4bit_use_double_quant'])
            prepare.assert_called_once()

    def test_two_visible_gpus_are_rejected_before_base_loading(self):
        with patch('torch.cuda.is_available', return_value=True), \
             patch('torch.cuda.device_count', return_value=2), \
             patch('transformers.AutoModelForCausalLM.from_pretrained') as loader:
            with self.assertRaisesRegex(ValueError, 'NO_DATAPARALLEL'):
                load_training_model(self.config)
            loader.assert_not_called()

    def test_training_arguments_do_not_allow_implicit_dataparallel(self):
        with patch('transformers.TrainingArguments', return_value=SimpleNamespace(n_gpu=2, world_size=1)):
            with self.assertRaisesRegex(ValueError, 'NO_DATAPARALLEL'):
                training_arguments(self.config, 'smoke', 'unused')

    def test_failed_training_preserves_primary_error_without_tensor_readback(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as name:
            trainer = SimpleNamespace(state=SimpleNamespace(global_step=0),
                train=Mock(side_effect=RuntimeError('ORIGINAL_CUDA_FAILURE')))
            callback = SimpleNamespace(applied=0, skipped=0,
                report=Mock(side_effect=RuntimeError('SECONDARY_COPY_FAILURE')))
            with patch('transformers.Trainer', return_value=trainer), \
                 patch('scripts.qlora.runtime.make_callbacks', return_value=callback):
                with self.assertRaisesRegex(RuntimeError, 'ORIGINAL_CUDA_FAILURE'):
                    fit(None, {'train': [], 'validation': []}, None, SimpleNamespace(use_cpu=True),
                        Path(name), self.config)
            callback.report.assert_not_called()
            report = read_json(Path(name) / 'training-failure.json')
            self.assertEqual(report['error'], 'ORIGINAL_CUDA_FAILURE')
            self.assertIsNone(report['adapter_delta_l2'])

    def test_skipped_optimizer_count_and_stop_control(self):
        with tempfile.TemporaryDirectory() as name:
            callback = make_callbacks(Path(name), self.config, stop_after_step=26)
            callback.trainer = SimpleNamespace(accelerator=SimpleNamespace(optimizer_step_was_skipped=True))
            callback.started = 0
            control = SimpleNamespace(should_save=False, should_evaluate=False, should_training_stop=False)
            callback.on_step_end(None, SimpleNamespace(global_step=26), control)
            self.assertEqual((callback.applied, callback.skipped), (0, 1))
            self.assertTrue(control.should_save and control.should_evaluate and control.should_training_stop)

    def test_nonfinite_loss_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            callback = make_callbacks(Path(name), self.config)
            with self.assertRaisesRegex(ValueError, 'NONFINITE_TRAINING_LOG'):
                callback.on_log(None, SimpleNamespace(global_step=1), None, logs={'loss': float('nan')})

    def test_missing_or_nonfinite_gradient_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            model = tiny_model()
            callback = make_callbacks(Path(name), self.config)
            with self.assertRaisesRegex(ValueError, 'NO_ADAPTER_GRADIENT'):
                callback.on_pre_optimizer_step(None, None, None, model=model)
            parameter = next(iter(adapter_parameters(model).values()))
            parameter.grad = torch.full_like(parameter, float('nan'))
            with self.assertRaisesRegex(ValueError, 'NONFINITE_GRADIENT'):
                callback.on_pre_optimizer_step(None, None, None, model=model)

    def test_recipe_preserves_pilot_scheduler_during_resume(self):
        args = training_arguments(self.config, 'pilot', 'unused', cpu_test=True)
        self.assertEqual(args.max_steps, 50)
        self.assertEqual(args.warmup_ratio, 0.1)
        self.assertFalse(args.logging_nan_inf_filter)

    def test_resume_requires_receipt_and_full_training_state(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            checkpoint = root / 'checkpoint-25'
            checkpoint.mkdir()
            for file in ('adapter_config.json', 'adapter_model.safetensors', 'optimizer.pt',
                         'scheduler.pt', 'rng_state.pth', 'scaler.pt'):
                (checkpoint / file).write_bytes(b'fixture-not-loadable-training-state')
            write_json(checkpoint / 'trainer_state.json', {'global_step': 25})
            write_json(checkpoint / 'binding.json', {'config_sha256': digest(self.config),
                       'data_manifest_sha256': self.config['data_manifest_sha256']})
            finish_manifest(root, status='TRAINING_COMPLETED', profile='pilot', config=self.config)
            expected = sha_file(root / 'run-manifest.json')
            self.assertEqual(resume_checkpoint(checkpoint, expected, self.config, 26), checkpoint)
            with self.assertRaisesRegex(ValueError, 'RESUME_RECEIPT_REQUIRED'):
                resume_checkpoint(checkpoint, None, self.config, 26)
            with self.assertRaisesRegex(ValueError, 'RESUME_MANIFEST_HASH'):
                resume_checkpoint(checkpoint, '0' * 64, self.config, 26)
            with self.assertRaisesRegex(ValueError, 'RESUME_STOP_26'):
                resume_checkpoint(checkpoint, expected, self.config, 27)
            (checkpoint / 'scaler.pt').unlink()
            with self.assertRaises(ValueError):
                resume_checkpoint(checkpoint, expected, self.config, 26)

    def test_actual_cpu_training_update_checkpoint_and_resume(self):
        torch.set_num_threads(1)
        config = deepcopy(self.config)
        # Tiny random model test: never claim this is the Qwen 7B/NF4 GPU smoke.
        config['training']['optim'] = 'adamw_torch'
        config['training']['learning_rate'] = 0.01
        config['profiles']['pilot'] = {'max_steps': 4, 'save_steps': 2, 'eval_steps': 2}
        example = {'input_ids': [3, 4, 5, 6, 2, 7], 'attention_mask': [1] * 6,
                   'labels': [-100, -100, 5, 6, 2, -100]}
        data = {'train': [deepcopy(example) for _ in range(4)], 'validation': [example]}
        with tempfile.TemporaryDirectory() as name:
            first, second = Path(name) / 'first', Path(name) / 'resume'
            first.mkdir()
            second.mkdir()
            model = tiny_model()
            base = {n: p.detach().clone() for n, p in model.named_parameters() if not p.requires_grad}
            trainer, update = fit(model, data, CompletionCollator(0, 2),
                training_arguments(config, 'pilot', first, cpu_test=True), first, config,
                stop_after_step=2)
            self.assertEqual(update['applied_updates'], 2)
            self.assertGreater(update['adapter_delta_l2'], 0)
            self.assertTrue(all(torch.equal(base[n], p) for n, p in model.named_parameters() if n in base))
            checkpoint = first / 'checkpoint-2'
            for file in ('optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'adapter_model.safetensors'):
                self.assertTrue((checkpoint / file).is_file(), file)
            _, resumed = fit(tiny_model(), data, CompletionCollator(0, 2),
                training_arguments(config, 'pilot', second, cpu_test=True), second, config,
                resume=checkpoint, stop_after_step=3)
            self.assertEqual((resumed['start_global_step'], resumed['global_step'],
                              resumed['applied_updates']), (2, 3, 1))
            self.assertGreater(resumed['adapter_delta_l2'], 0)
            from peft import PeftModel, get_peft_model_state_dict
            # A new model object reloads the persisted adapter tensors, without network access.
            reloaded = PeftModel.from_pretrained(tiny_base(), second / 'final-adapter')
            self.assertTrue((second / 'final-adapter/adapter_model.safetensors').exists())
            with torch.no_grad():
                self.assertTrue(torch.isfinite(reloaded(**CompletionCollator(0, 2)([example])).loss))
            from safetensors.torch import load_file
            stored = load_file(second / 'final-adapter/adapter_model.safetensors')
            restored = get_peft_model_state_dict(reloaded)
            self.assertEqual(set(stored), set(restored))
            self.assertTrue(all(torch.equal(stored[n], restored[n]) for n in stored))
            type(self).cpu_proof = dict(first_run=update, resume=resumed,
                frozen_base_unchanged=True, reloaded_adapter_tensors_exact=True,
                scope='TINY_RANDOM_CPU_MODEL_NOT_QWEN_7B_NF4')
