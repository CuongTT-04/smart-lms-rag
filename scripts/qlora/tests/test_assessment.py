"""CPU verification tests; never evidence of a Qwen 7B GPU reload/resume."""
import ast
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.qlora.assessment import (GENERATION, PILOT_SHA, automatic_checks, cases_from_bundle,
    audit_resume, check_run, find_pilot, prompt_ids, score_generation, summarize, verify_loaded_adapter)
from scripts.qlora.data import digest, read_json, sha_file
from scripts.qlora.runtime import finish_manifest, write_json
from scripts.qlora.tests.test_runtime import tiny_model

ROOT = Path(__file__).resolve().parents[3]


def case():
    return dict(record_id='case-1', task_type='qa', evidence=[{'evidence_id': 'E1.1', 'text': 'A fact'}],
        prompt=[{'role': 'system', 'content': 'Use evidence.'}, {'role': 'user', 'content': 'Question and evidence'}],
        reference='{"items":[{"text":"A fact","evidence_id":"E1.1"}]}')


class AssessmentTests(unittest.TestCase):
    def test_partial_valid_json_or_hint_never_passes_without_completed_generation(self):
        c = case()
        for status in ('OUTPUT_LIMIT', 'INCOMPLETE_OR_TIMEOUT'):
            checks = score_generation(c['reference'], c, status)
            self.assertFalse(checks['format_valid'])
            self.assertFalse(checks['expected_behavior_match'])
            self.assertEqual(checks['reference_token_f1'], 0)

    def test_format_and_known_citation_do_not_assert_semantic_quality(self):
        c = case()
        result = automatic_checks(c['reference'], c)
        self.assertTrue(result['format_valid'] and result['citation_ids_valid'])
        self.assertTrue(result['expected_behavior_match'] and result['reference_exact_match'])
        self.assertIsNone(result['semantic_correctness'])
        self.assertIsNone(result['grounded'])
        self.assertIsNone(result['citation_supports_claim'])

    def test_unknown_id_duplicate_keys_and_extra_text_are_rejected(self):
        c = case()
        self.assertFalse(automatic_checks(c['reference'].replace('E1.1', 'E9.9'), c)['citation_ids_valid'])
        for text in ('{"items":[],"items":[]}', '```json\n' + c['reference'] + '\n```',
                     '{"items":[{"text":"A fact","evidence_id":"E1.1","quote":"x"}]}'):
            self.assertFalse(automatic_checks(text, c)['format_valid'])

    def test_abstention_does_not_count_as_normal_answer(self):
        c = case()
        result = automatic_checks('{"items":[]}', c)
        self.assertTrue(result['format_valid'])
        self.assertFalse(result['expected_behavior_match'])
        c.update(task_type='insufficient_evidence', reference='{"items":[]}')
        self.assertTrue(automatic_checks('{"items":[]}', c)['expected_behavior_match'])

    def test_hint_action_grammar_cannot_certify_hint_quality(self):
        c = case()
        c.update(task_type='hint', reference='READ [1]', evidence=[{'citation_label': 1, 'source_id': 'S1'},
                    {'citation_label': 2, 'source_id': 'S1'}])
        self.assertTrue(automatic_checks('READ [1]', c)['hint_action_only'])
        self.assertFalse(automatic_checks('READ [1] answer is 42', c)['format_valid'])
        self.assertFalse(automatic_checks('COMPARE [1] [2]', c)['citation_ids_valid'])
        self.assertFalse(automatic_checks('READ [99]', c)['citation_ids_valid'])

    def test_reference_never_reaches_tokenizer_or_generation(self):
        c = case()
        tokenizer = SimpleNamespace(apply_chat_template=Mock(return_value=[1, 2, 3]))
        ids = prompt_ids(c, tokenizer, {'token_limits': {'max_prompt_tokens': 3}})
        self.assertEqual(ids, [1, 2, 3])
        tokenizer.apply_chat_template.assert_called_once_with(c['prompt'], tokenize=True, add_generation_prompt=True)
        with self.assertRaisesRegex(ValueError, 'PROMPT_BUDGET'):
            prompt_ids(c, tokenizer, {'token_limits': {'max_prompt_tokens': 2}})

    def test_summary_counts_all_40_cases_and_preserves_semantic_unknowns(self):
        rows = [dict(record_id=str(i), arm=arm, status='COMPLETED', checks=automatic_checks(case()['reference'], case()),
                     latency_seconds=1, input_tokens=10, output_tokens=5)
                for i in range(20) for arm in ('base', 'adapter')]
        result = summarize(rows)
        self.assertEqual(result['arms']['base']['format_valid'], 20)
        self.assertEqual(result['semantic_quality'], 'NOT_REVIEWED')
        self.assertFalse(result['human_review_complete'])
        with self.assertRaisesRegex(ValueError, 'FORTY'):
            summarize(rows[:-1])

    def test_locked_selection_reads_only_validation_and_does_not_mutate_prompt(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / 'data/pilot-v2'
            root.mkdir(parents=True)
            ids = ['id-' + str(i) for i in range(20)]
            write_json(root / 'evaluation-selection.json', dict(record_ids=ids, count=20,
                scope='DEVELOPMENT_VALIDATION_NOT_HELDOUT_TEST', selected_before_adapter_outputs=True))
            payload = dict(prompt=case()['prompt'], completion=[{'role': 'assistant', 'content': case()['reference']}])
            payload['prompt'][-1]['content'] = json.dumps({'evidence': case()['evidence']})
            (root / 'validation.jsonl').write_text(''.join(json.dumps(payload) + '\n' for _ in ids), encoding='utf-8')
            metadata = [dict(source_record_id=rid, training_payload_sha256=digest(payload), task_type='qa', split='validation') for rid in ids]
            (root / 'validation.metadata.jsonl').write_text(''.join(json.dumps(m) + '\n' for m in metadata), encoding='utf-8')
            with patch('scripts.qlora.assessment.authenticate'):
                cases = cases_from_bundle(Path(name), {})
                self.assertEqual([r['record_id'] for r in cases], ids)
                self.assertEqual(cases[0]['prompt'], payload['prompt'])
                selection = read_json(root / 'evaluation-selection.json')
                selection['record_ids'][0] = 'missing'
                write_json(root / 'evaluation-selection.json', selection)
                with self.assertRaisesRegex(ValueError, 'NOT_VALIDATION'):
                    cases_from_bundle(Path(name), {})

    def test_actual_tiny_cpu_adapter_reload_not_qwen7b_gpu(self):
        import torch
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            original = tiny_model()
            with torch.no_grad():
                for key, parameter in original.named_parameters():
                    if 'lora_B' in key:
                        parameter.fill_(0.01)
            original.save_pretrained(folder)
            restored = tiny_model()
            restored.load_adapter(str(folder), adapter_name='pilot', is_trainable=False)
            restored.set_adapter('pilot')
            restored.requires_grad_(False)
            restored.eval()
            verify_loaded_adapter(restored, folder)
            inputs = torch.tensor([[3, 4, 5]])
            with torch.no_grad():
                adapted = restored(inputs).logits
                with restored.disable_adapter():
                    base = restored(inputs).logits
            self.assertFalse(torch.equal(adapted, base))
            with torch.no_grad():
                for key, parameter in restored.named_parameters():
                    if 'lora_B.pilot' in key:
                        parameter.add_(1)
            with self.assertRaisesRegex(ValueError, 'TENSORS_DIFFER'):
                verify_loaded_adapter(restored, folder)


class ResumeAuditTests(unittest.TestCase):
    def fixture(self, root):
        import torch
        from safetensors.torch import save_file
        config = read_json(ROOT / 'configs/qlora-pilot.json')
        original = root / 'original'
        output = root / 'verification'
        run = output / 'resume'
        (original / 'checkpoint-25').mkdir(parents=True)
        (run / 'checkpoint-26').mkdir(parents=True)
        (run / 'final-adapter').mkdir()
        for folder, step in ((original / 'checkpoint-25', 25), (run / 'checkpoint-26', 26)):
            torch.save({'last_epoch': step, 'base_lrs': [0.0002]}, folder / 'scheduler.pt')
            torch.save({'state': {0: {'step': step, 'state1': torch.ones(2)}}}, folder / 'optimizer.pt')
        save_file({'a.lora_A.weight': torch.ones(2)}, run / 'final-adapter/adapter_model.safetensors')
        save_file({'a.lora_A.weight': torch.ones(2)}, run / 'checkpoint-26/adapter_model.safetensors')
        write_json(run / 'training-arguments.json', dict(config['training'], max_steps=50, fp16=True, bf16=False))
        write_json(run / 'environment.json', dict(cuda_available=True, gpus=['Tesla T4']))
        write_json(run / 'training-device.json', dict(world_size=1, visible_gpu_count=1))
        write_json(run / 'model-load-report.json', dict(model_id=config['model_id'], revision=config['revision'], is_loaded_in_4bit=True))
        write_json(run / 'data-reference.json', dict(resume_checkpoint=str(original / 'checkpoint-25'), resume_manifest_sha256=PILOT_SHA))
        write_json(run / 'adapter-update-report.json', dict(start_global_step=25, global_step=26,
            applied_updates=1, attempted_updates=1, finite_gradient_checks=1, scaler_skipped_updates=0,
            base_frozen=True, adapter_delta_l2=0.1))
        (run / 'optimizer-events.jsonl').write_text('{"step":26,"update_applied":true}\n', encoding='utf-8')
        write_json(run / 'checkpoint-26/trainer_state.json', {'global_step': 26})
        write_json(run / 'eval-metrics.json', {'eval_loss': 0.3})
        for path in (original, run):
            finish_manifest(path, status='TRAINING_COMPLETED', profile='pilot', config=config)
        return output, run, original, config

    def test_synthetic_resume_proof_not_gpu_execution(self):
        with tempfile.TemporaryDirectory() as name:
            output, run, original, config = self.fixture(Path(name))
            with patch('scripts.qlora.assessment.load_context', return_value=({'pilot': str(original)}, config)):
                report = audit_resume(output)
            self.assertEqual(report['status'], 'GPU_RESUME_PASSED')
            self.assertEqual(report['optimizer_state_steps_after'], [26])
            self.assertEqual(report['applied_updates'], 1)

    def test_optimizer_or_scheduler_restart_cannot_pass_as_resume(self):
        import torch
        for state in ('optimizer', 'scheduler'):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as name:
                output, run, original, config = self.fixture(Path(name))
                file = run / ('checkpoint-26/' + state + '.pt')
                data = torch.load(file, weights_only=True)
                if state == 'optimizer':
                    data['state'][0]['step'] = 1
                else:
                    data['last_epoch'] = 1
                torch.save(data, file)
                finish_manifest(run, status='TRAINING_COMPLETED', profile='pilot', config=config)
                with patch('scripts.qlora.assessment.load_context', return_value=({'pilot': str(original)}, config)):
                    with self.assertRaisesRegex(ValueError, 'NOT_RESTORED'):
                        audit_resume(output)

    def test_changed_run_file_fails_integrity_before_resume_claim(self):
        with tempfile.TemporaryDirectory() as name:
            output, run, original, config = self.fixture(Path(name))
            write_json(run / 'eval-metrics.json', {'eval_loss': 0.1})
            with patch('scripts.qlora.assessment.load_context', return_value=({'pilot': str(original)}, config)):
                with self.assertRaisesRegex(ValueError, 'ARTIFACT_INTEGRITY'):
                    audit_resume(output)


@unittest.skipUnless((ROOT / 'notebooks/qlora_verification.ipynb').exists(), 'Repository-only notebook')
class VerificationNotebookTests(unittest.TestCase):
    def notebook(self):
        return read_json(ROOT / 'notebooks/qlora_verification.ipynb')

    def test_six_cells_and_only_one_resume_step_not_pilot_retraining(self):
        notebook = self.notebook()
        code = [c for c in notebook['cells'] if c['cell_type'] == 'code']
        self.assertEqual(len(code), 6)
        for cell in code:
            compile(''.join(cell['source']), 'verification-cell', 'exec')
        resume = ''.join(code[4]['source'])
        self.assertIn("'--stop-after-step', '26'", resume)
        self.assertIn("'--resume-from-checkpoint'", resume)
        self.assertIn('FROZEN_TOOLS', resume)
        self.assertNotIn('gpu-pilot', [c.get('id') for c in code])
        self.assertEqual(notebook['metadata']['ohayo_gpu_verification']['pilot_manifest_sha256'], PILOT_SHA)

    def test_frozen_sources_keep_original_hashes_and_worker_sources_match_repo(self):
        notebook = self.notebook()
        code = ''.join(next(c for c in notebook['cells'] if c.get('id') == 'reload-comparison')['source'])
        variables = {}
        for node in ast.parse(code).body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('VERIFY_SOURCES', 'FROZEN_SOURCES', 'FROZEN_HASHES'):
                variables[node.targets[0].id] = ast.literal_eval(node.value)
        for name, text in variables['VERIFY_SOURCES'].items():
            self.assertEqual(text, (ROOT / 'scripts/qlora' / name).read_text(encoding='utf-8'))
        for name, text in variables['FROZEN_SOURCES'].items():
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), variables['FROZEN_HASHES'][name])
        self.assertNotIn('assessment.py', variables['FROZEN_SOURCES'])
        self.assertIn('assessment.py', variables['VERIFY_SOURCES'])

    def test_notebook_runtime_overlay_and_resume_launch_without_gpu(self):
        import datetime, shutil, subprocess, sys
        code = [c for c in self.notebook()['cells'] if c['cell_type'] == 'code']
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            original = root / 'tools-environment'
            (original / 'scripts/qlora').mkdir(parents=True)
            (original / 'scripts/qlora/setup.py').write_bytes(b'# original setup\n')
            report = root / 'report'
            report.mkdir()
            write_json(report / 'environment-check.json', {'status': 'ENVIRONMENT_READY_FOR_SMOKE'})
            namespace = dict(Path=Path, WORK=root, RUN_TOOLS=original, REPORT=report,
                HANDOFF=root / 'handoff', VENV=root / 'venv', sys=sys, hashlib=hashlib,
                json=json, shutil=shutil, subprocess=subprocess,
                datetime=datetime.datetime, timezone=datetime.timezone)
            process = SimpleNamespace(poll=lambda: 0, returncode=0)
            def prepare(command, **kwargs):
                out = Path(command[command.index('--output') + 1])
                out.mkdir(parents=True)
                write_json(out / 'context.json', dict(pilot=str(root / 'original-pilot'), pilot_manifest_sha256=PILOT_SHA))
            with patch('subprocess.run', side_effect=prepare), patch('subprocess.Popen', return_value=process) as spawn, redirect_stdout(io.StringIO()):
                exec(compile(''.join(code[3]['source']), 'reload-cell', 'exec'), namespace)
            command = spawn.call_args.args[0]
            self.assertEqual(command[command.index('--stage') + 1], 'evaluate')
            self.assertEqual(spawn.call_args.kwargs['env']['CUDA_VISIBLE_DEVICES'], '0')
            self.assertEqual((original / 'scripts/qlora/setup.py').read_bytes(), b'# original setup\n')
            (namespace['VERIFY_DIR'] / 'evaluation').mkdir()
            write_json(namespace['VERIFY_DIR'] / 'evaluation/comparison.json', {})
            helper = Mock()
            namespace['run_verified_process'] = helper
            with redirect_stdout(io.StringIO()):
                exec(compile(''.join(code[4]['source']), 'resume-cell', 'exec'), namespace)
            command = helper.call_args.args[0]
            self.assertEqual(command[command.index('--stop-after-step') + 1], '26')
            self.assertIn('checkpoint-25', command[command.index('--resume-from-checkpoint') + 1])
            self.assertEqual(helper.call_args.args[1], namespace['FROZEN_TOOLS'])
            with patch('subprocess.Popen') as spawn, self.assertRaisesRegex(RuntimeError, 'already running'):
                namespace['VERIFY_PROCESS'] = SimpleNamespace(poll=lambda: None)
                exec(compile(''.join(code[3]['source']), 'duplicate-cell', 'exec'), namespace)
            spawn.assert_not_called()
