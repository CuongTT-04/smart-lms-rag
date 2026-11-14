import ast
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts.comparison.package_training import notebook
from scripts.comparison.protocol import write_bundle, write_json
from scripts.comparison.training import (COUNTS, LORA, MODEL, REVISION, TRAINING,
                                         arguments, fit, validate_config)
from scripts.comparison.training_report import FIGURES, render, series
from scripts.comparison.training_audit import export


def config():
    return dict(schema_version='comparison-training-v1',model_id=MODEL,revision=REVISION,
        training=deepcopy(TRAINING),lora=deepcopy(LORA),seed=42,epochs=1,counts=dict(COUNTS),
        holdout_included=False,expected_updates=193,eval_steps=25,save_steps=50,
        initialization='PINNED_BASE_FRESH_LORA',selection='FINAL_EPOCH_NOT_BEST_ON_HOLDOUT',
        main_authorized=False,data_manifest_sha256='a'*64,
        token_limits=dict(max_sequence_tokens=32))


class ConfigurationTests(unittest.TestCase):
    def test_valid_config(self):
        validate_config(config())

    def test_changes_rejected(self):
        changes=dict(model_id='other',revision='b'*40,epochs=2,expected_updates=192,
                     holdout_included=True,initialization='RESUME_PILOT',main_authorized=True)
        for key,value in changes.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config(dict(config(),**{key:value}))

    def test_recipe_changes_rejected(self):
        value=config()
        value['training']['gradient_accumulation_steps']=8
        with self.assertRaisesRegex(ValueError,'RECIPE_CHANGED'):
            validate_config(value)

    def test_epoch_not_max_steps(self):
        with tempfile.TemporaryDirectory() as folder:
            args=arguments(config(),Path(folder),770,'full',cpu_test=True)
            self.assertEqual(args.num_train_epochs,1)
            self.assertEqual(args.max_steps,-1)
            self.assertEqual(args.gradient_accumulation_steps,4)
            self.assertEqual(args.eval_steps,25)
            self.assertFalse(args.load_best_model_at_end)

    def test_smoke_explicit_two_steps(self):
        with tempfile.TemporaryDirectory() as folder:
            args=arguments(config(),Path(folder),770,'smoke',cpu_test=True)
            self.assertEqual((args.max_steps,args.eval_steps,args.save_steps),(2,2,2))


class TrainingNotebookTests(unittest.TestCase):
    def make(self,folder):
        folder=Path(folder)
        source=folder/'contents'
        source.mkdir()
        (source/'safe.txt').write_text('fixture',encoding='utf-8')
        archive=folder/'training-runner.zip'
        receipt=write_bundle(source,archive)
        path=folder/'training.ipynb'
        notebook(path,archive,receipt)
        return [''.join(c['source']) for c in json.loads(path.read_text(encoding='utf-8'))['cells'] if c['cell_type']=='code']

    def test_five_cells_compile_and_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            cells=self.make(folder)
            self.assertEqual(len(cells),5)
            for cell in cells:
                ast.parse(cell)
            self.assertIn('training-runner.zip',cells[0])
            self.assertIn('CUDA_VISIBLE_DEVICES',cells[0])
            self.assertIn('training_kaggle',cells[1])
            self.assertIn("train_run('smoke')",cells[2])
            self.assertIn("assert TRAIN_SMOKE_AUDIT['status']",cells[3])
            self.assertIn("train_run('full')",cells[3])
            self.assertIn("execute('dev')",cells[4])
            self.assertNotIn("execute('main')",''.join(cells))

    def test_failed_runs_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            cells=self.make(folder)
            self.assertIn('-failed.zip',cells[2])
            self.assertIn("zipfile.ZipFile(archive, 'x'",cells[2])


def logs(folder):
    folder=Path(folder)
    rows=[dict(step=0,eval_loss=1.5)]
    for step in (1,2):
        rows.append(dict(step=step,loss=1/step,learning_rate=0.0001,grad_norm=0.2,epoch=step/2))
    rows.append(dict(step=2,eval_loss=0.9))
    (folder/'train-metrics.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    resources=[dict(step=s,epoch=s/2,elapsed_seconds=s*2,cumulative_updates_per_second=0.5,
        allocated_bytes=100,reserved_bytes=200,peak_allocated_bytes=120,peak_reserved_bytes=200) for s in (1,2)]
    (folder/'resource-metrics.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in resources),encoding='utf-8')


class FigureTests(unittest.TestCase):
    def test_png_csv_and_no_interpretation_inside_figures(self):
        import matplotlib.figure
        from PIL import Image
        saved=[]
        original=matplotlib.figure.Figure.savefig
        def save(fig,*args,**kwargs):
            saved.extend(t.get_text() for t in fig.findobj() if hasattr(t,'get_text'))
            return original(fig,*args,**kwargs)
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            logs(folder)
            with patch.object(matplotlib.figure.Figure,'savefig',save):
                render(folder,folder/'figures')
            self.assertEqual(len(list((folder/'figures').glob('*.png'))),4)
            for name in FIGURES:
                with Image.open(folder/'figures'/name) as im:
                    self.assertGreaterEqual(im.width,1000)
                    extrema=im.convert('RGB').getextrema()
                    self.assertTrue(any(hi-lo>100 for lo,hi in extrema))
            self.assertFalse(any(any(w in s.lower() for w in ('overfit','improvement','does not','not establish')) for s in saved))
            self.assertTrue((folder/'figures/metrics.csv').is_file())
            with self.assertRaisesRegex(ValueError,'OUTPUT_EXISTS'):
                render(folder,folder/'figures')

    def test_missing_steps_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            logs(folder)
            path=folder/'resource-metrics.jsonl'
            path.write_text(path.read_text().splitlines()[0]+'\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'COVERAGE'):
                series(folder)

    def test_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            logs(folder)
            path=folder/'train-metrics.jsonl'
            path.write_text(path.read_text().replace('1.5','NaN'),encoding='utf-8')
            with self.assertRaises(ValueError):
                series(folder)


class ExportTests(unittest.TestCase):
    def test_zip_keeps_exact_run_file_set_and_separate_audit(self):
        from zipfile import ZipFile
        from scripts.qlora.data import sha_file
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            run=folder/'full-fixture'
            run.mkdir()
            (run/'run-manifest.json').write_text('{}',encoding='utf-8')
            (run/'raw-log.json').write_text('{}',encoding='utf-8')
            report=dict(status='FIXTURE_ONLY',run_manifest_sha256=sha_file(run/'run-manifest.json'))
            with patch('scripts.comparison.training_audit.audit',return_value=report):
                export(run,folder/'package')
            with ZipFile(folder/'full-fixture.zip') as archive:
                self.assertEqual(set(archive.namelist()),{'run-manifest.json','raw-log.json'})
            receipt=json.loads((folder/'full-fixture-receipt.json').read_text())
            self.assertEqual(receipt['sha256'],sha_file(folder/'full-fixture.zip'))
            self.assertEqual(receipt['audit_sha256'],sha_file(folder/'full-fixture-audit.json'))


class RealTrainingTests(unittest.TestCase):
    def test_one_epoch_includes_final_short_accumulation_and_saves_final(self):
        import torch
        from peft import LoraConfig,get_peft_model
        from transformers import GPT2Config,GPT2LMHeadModel
        model=get_peft_model(GPT2LMHeadModel(GPT2Config(n_layer=1,n_head=1,n_embd=8,vocab_size=16,
            n_positions=32,pad_token_id=0,eos_token_id=2,use_cache=False)),
            LoraConfig(r=2,lora_alpha=4,target_modules=['c_attn'],task_type='CAUSAL_LM'))
        seen=[]
        def record(module,args,kwargs):
            if module.training:
                seen.extend(kwargs['input_ids'][:,0].tolist())
        model.register_forward_pre_hook(record,with_kwargs=True)
        def row(i):
            return dict(input_ids=[i,6,7,8,9,2],attention_mask=[1]*6,labels=[-100]*3+[8,9,2])
        data=dict(train=[row(i) for i in range(1,6)],validation=[row(1)])
        tokenizer=SimpleNamespace(pad_token_id=0,eos_token_id=2)
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            result=fit(model,data,tokenizer,config(),folder,'full',cpu_test=True)
            self.assertEqual(result['applied_updates'],2)
            self.assertEqual(sorted(seen),list(range(1,6)))
            self.assertTrue((folder/'checkpoint-2/optimizer.pt').is_file())
            self.assertTrue((folder/'final-adapter/adapter_model.safetensors').is_file())
            evaluation=[json.loads(s)['step'] for s in (folder/'train-metrics.jsonl').read_text().splitlines() if 'eval_loss' in json.loads(s)]
            self.assertEqual(evaluation,[0,2])


if __name__=='__main__':
    unittest.main()
