from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import torch
from safetensors.torch import save_file

from scripts.qlora.data import digest, read_json
from scripts.qlora.runtime import finish_manifest, write_json
from scripts.qlora.smoke import audit

RECIPE = Path(__file__).resolve().parents[3] / 'configs/qlora-pilot.json'


class SmokeAuditTests(unittest.TestCase):
    def fixture(self, root):
        config = read_json(RECIPE)
        checkpoint = root / 'checkpoint-2'
        final = root / 'final-adapter'
        checkpoint.mkdir()
        final.mkdir()
        tensors = {'layer.lora_A.weight': torch.ones(8, 2), 'layer.lora_B.weight': torch.ones(2, 8)}
        for folder in (checkpoint, final):
            save_file(tensors, folder / 'adapter_model.safetensors')
            write_json(folder / 'adapter_config.json', config['lora'])
        for name in ('optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'scaler.pt'):
            (checkpoint / name).write_bytes(b'CPU-test fixture; not loadable GPU state')
        write_json(checkpoint / 'trainer_state.json', {'global_step': 2})
        write_json(checkpoint / 'binding.json', dict(config_sha256=digest(config),
                   data_manifest_sha256=config['data_manifest_sha256']))
        write_json(root / 'resolved-config.json', config)
        write_json(root / 'data-reference.json', dict(train=128, validation=32, holdout=0,
                   manifest_sha256=config['data_manifest_sha256'], contract_sha256=config['contract_sha256']))
        write_json(root / 'training-arguments.json', dict(max_steps=2, fp16=True, bf16=False,
                   gradient_accumulation_steps=4, per_device_train_batch_size=1))
        write_json(root / 'environment.json', dict(cuda_available=True, cuda='fixture', gpus=['Tesla T4']))
        write_json(root / 'training-device.json', dict(visible_gpu_count=1, world_size=1,
                   mode='SINGLE_GPU_NO_DATAPARALLEL'))
        write_json(root / 'model-load-report.json', dict(model_id=config['model_id'], revision=config['revision'],
                   is_loaded_in_4bit=True, use_cache=False, quantization=dict(
                       bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True)))
        write_json(root / 'adapter-update-report.json', dict(start_global_step=0, global_step=2,
                   attempted_updates=2, applied_updates=2, scaler_skipped_updates=0,
                   finite_gradient_checks=2, adapter_delta_l2=0.1, base_frozen=True))
        (root / 'optimizer-events.jsonl').write_text(
            '{"step":1,"update_applied":true}\n{"step":2,"update_applied":true}\n', encoding='utf-8')
        (root / 'train-metrics.jsonl').write_text(
            '{"step":1,"loss":2.0}\n{"step":2,"loss":1.5}\n', encoding='utf-8')
        write_json(root / 'eval-metrics.json', {'eval_loss': 1.6})
        write_json(root / 'storage-check.json', {'passed': True})
        write_json(root / 'trainable-parameters.json', {'base_frozen': True, 'trainable_parameters': 32})
        write_json(root / 'vram.json', {'peak_allocated_bytes': 100, 'peak_reserved_bytes': 200})
        self.seal(root)

    def seal(self, root):
        finish_manifest(root, status='TRAINING_COMPLETED', profile='smoke', config=read_json(RECIPE))

    def test_valid_synthetic_evidence_not_a_real_gpu_run(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root)
            self.assertEqual(audit(root)['status'], 'GPU_SMOKE_PASSED')

    def test_zero_delta_skipped_update_or_unfrozen_base_cannot_pass(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root)
            original = read_json(root / 'adapter-update-report.json')
            for key, value in (('adapter_delta_l2', 0), ('scaler_skipped_updates', 1),
                               ('applied_updates', 1), ('base_frozen', False)):
                write_json(root / 'adapter-update-report.json', dict(original, **{key: value}))
                self.seal(root)
                with self.assertRaisesRegex(ValueError, 'SMOKE_OPTIMIZER_PROOF'):
                    audit(root)

    def test_missing_checkpoint_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root)
            (root / 'checkpoint-2/scaler.pt').unlink()
            self.seal(root)
            with self.assertRaisesRegex(ValueError, 'CHECKPOINT_INCOMPLETE'):
                audit(root)

    def test_cpu_run_or_tensor_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root)
            write_json(root / 'environment.json', dict(cuda_available=False, cuda=None, gpus=[]))
            self.seal(root)
            with self.assertRaisesRegex(ValueError, 'GPU_EVIDENCE_REQUIRED'):
                audit(root)
            write_json(root / 'environment.json', dict(cuda_available=True, cuda='fixture', gpus=['Tesla T4']))
            save_file({'layer.lora_A.weight': torch.zeros(8, 2), 'layer.lora_B.weight': torch.ones(2, 8)},
                      root / 'final-adapter/adapter_model.safetensors')
            self.seal(root)
            with self.assertRaisesRegex(ValueError, 'SAVED_TENSORS_DIFFER'):
                audit(root)

    def test_tampering_after_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root)
            (root / 'storage-check.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'ARTIFACT_INTEGRITY'):
                audit(root)
