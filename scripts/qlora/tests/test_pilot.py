"""Synthetic evidence tests only; these never claim an actual GPU pilot."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.qlora.data import read_json
from scripts.qlora.pilot import audit, main
from scripts.qlora.runtime import finish_manifest, write_json
from scripts.qlora.tests import test_smoke

RECIPE = test_smoke.RECIPE


class PilotAuditTests(unittest.TestCase):
    def fixture(self, root):
        test_smoke.SmokeAuditTests().fixture(root)
        (root / 'checkpoint-2').rename(root / 'checkpoint-50')
        import shutil
        shutil.copytree(root / 'checkpoint-50', root / 'checkpoint-25')
        for step in (25, 50):
            folder = root / ('checkpoint-' + str(step))
            write_json(folder / 'trainer_state.json', {'global_step': step})
            binding = read_json(folder / 'binding.json')
            write_json(folder / 'binding.json', dict(binding, global_step=step))
            config = read_json(RECIPE)
            write_json(folder / 'adapter_config.json', dict(config['lora'],
                base_model_name_or_path=config['model_id'], revision=config['revision']))
        update = read_json(root / 'adapter-update-report.json')
        update.update(global_step=50, attempted_updates=50, applied_updates=50, finite_gradient_checks=50)
        write_json(root / 'adapter-update-report.json', update)
        args = read_json(root / 'training-arguments.json')
        args.update(max_steps=50, save_steps=25, eval_steps=25, save_total_limit=2)
        args.update(read_json(RECIPE)['training'], seed=42, data_seed=42, gradient_checkpointing=True)
        write_json(root / 'training-arguments.json', args)
        (root / 'optimizer-events.jsonl').write_text(''.join(
            json.dumps(dict(step=s, update_applied=True)) + '\n' for s in range(1, 51)), encoding='utf-8')
        self.logs(root)
        self.seal(root)

    def logs(self, root, evaluation_steps=(25, 50)):
        rows = [dict(step=s, loss=1.0) for s in range(1, 51)]
        rows += [dict(step=s, eval_loss=1.6) for s in evaluation_steps]
        (root / 'train-metrics.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')

    def seal(self, root):
        finish_manifest(root, status='TRAINING_COMPLETED', profile='pilot', config=read_json(RECIPE))

    def test_valid_fixture_exports_two_checkpoints_not_quality_claim(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / 'pilot-test'
            root.mkdir()
            self.fixture(root)
            report = audit(root)
            self.assertEqual(report['status'], 'GPU_PILOT_PASSED')
            self.assertEqual(report['applied_updates'], 50)
            self.assertEqual(report['checkpoints'], ['checkpoint-25', 'checkpoint-50'])
            self.assertEqual(report['quality_improvement'], 'NOT_ESTABLISHED')
            self.assertEqual(report['gpu_resume'], 'NOT_RUN')
            self.assertEqual(main(['--run', str(root)]), 0)
            receipt = read_json(root.with_name('pilot-test-receipt.json'))
            self.assertEqual(receipt['global_step'], 50)
            self.assertFalse(receipt['base_weights_included'])
            with self.assertRaisesRegex(ValueError, 'EXPORT_EXISTS'):
                main(['--run', str(root)])

    def test_missing_state_or_bad_binding_at_25_rejected(self):
        for fault in ('missing', 'binding'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                self.fixture(root)
                if fault == 'missing':
                    (root / 'checkpoint-25/optimizer.pt').unlink()
                else:
                    binding = read_json(root / 'checkpoint-25/binding.json')
                    write_json(root / 'checkpoint-25/binding.json', dict(binding, global_step=24))
                self.seal(root)
                with self.assertRaisesRegex(ValueError, 'PILOT_CHECKPOINT_'):
                    audit(root)

    def test_resume_or_wrong_eval_schedule_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root)
            ref = read_json(root / 'data-reference.json')
            write_json(root / 'data-reference.json', dict(ref, resume_checkpoint='checkpoint-2'))
            self.seal(root)
            with self.assertRaisesRegex(ValueError, 'MUST_START_FRESH'):
                audit(root)
            write_json(root / 'data-reference.json', ref)
            self.logs(root, (50,))
            self.seal(root)
            with self.assertRaisesRegex(ValueError, 'EVALUATION_STEPS'):
                audit(root)

    def test_49_updates_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root)
            update = read_json(root / 'adapter-update-report.json')
            write_json(root / 'adapter-update-report.json', dict(update, applied_updates=49))
            self.seal(root)
            with self.assertRaisesRegex(ValueError, 'OPTIMIZER_PROOF'):
                audit(root)

    def test_modified_recipe_or_adapter_identity_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root)
            args = read_json(root / 'training-arguments.json')
            write_json(root / 'training-arguments.json', dict(args, learning_rate=0.1))
            self.seal(root)
            with self.assertRaisesRegex(ValueError, 'TRAINING_RECIPE'):
                audit(root)
            write_json(root / 'training-arguments.json', args)
            adapter = read_json(root / 'checkpoint-25/adapter_config.json')
            write_json(root / 'checkpoint-25/adapter_config.json', dict(adapter, revision='other'))
            self.seal(root)
            with self.assertRaisesRegex(ValueError, 'ADAPTER_IDENTITY'):
                audit(root)

    def test_smoke_cannot_pass_as_pilot(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            test_smoke.SmokeAuditTests().fixture(root)
            with self.assertRaisesRegex(ValueError, 'NOT_COMPLETED'):
                audit(root)


class PilotNotebookTests(unittest.TestCase):
    def test_pilot_notebook_runs_only_pilot_and_embeds_reviewed_sources(self):
        path = RECIPE.parents[1] / 'notebooks/qlora_pilot.ipynb'
        if not path.exists():
            self.skipTest('Notebook not included in compact tools ZIP')
        notebook = read_json(path)
        code = [c for c in notebook['cells'] if c['cell_type'] == 'code']
        self.assertEqual(len(code), 5)
        self.assertNotIn('gpu-smoke', [c.get('id') for c in notebook['cells']])
        for cell in code:
            compile(''.join(cell['source']), 'pilot-cell', 'exec')
        training = ''.join(code[3]['source'])
        self.assertIn("'--profile', 'pilot'", training)
        self.assertIn("CUDA_VISIBLE_DEVICES='0'", training)
        self.assertIn("WORK / 'base-cache'", training)
        import ast
        tree = ast.parse(training)
        command = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                       and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'command')
        constants = [n.value for n in command.elts if isinstance(n, ast.Constant)]
        self.assertNotIn('--resume-from-checkpoint', constants)
        self.assertEqual(constants[constants.index('--profile') + 1], 'pilot')
        sources = next(ast.literal_eval(node.value) for node in tree.body
                       if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                       and node.targets[0].id == 'PILOT_SOURCES')
        for key, value in sources.items():
            self.assertEqual(value, (RECIPE.parents[1] / 'scripts/qlora' / key).read_text(encoding='utf-8'))
        self.assertIn('scripts.qlora.pilot', ''.join(code[4]['source']))
