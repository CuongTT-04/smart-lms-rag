"""Fresh one-epoch QLoRA, isolated from pilot artifacts and serving."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import time

from scripts.comparison.runner import MODEL, REVISION
from scripts.qlora.collator import CompletionCollator
from scripts.qlora.data import digest, read_json, read_rows, require, sha_file, tokenize_payload
from scripts.qlora.runtime import (inventory, load_training_model,
    make_callbacks, output_guard, parameter_report, verify_inventory, write_json)
from scripts.qlora.storage import check_training_storage
from scripts.comparison.training_environment import snapshot

ROOT = Path(__file__).resolve().parents[2]
COUNTS = dict(train=770, validation=114)
TRAINING = dict(learning_rate=0.0002, gradient_accumulation_steps=4,
    per_device_train_batch_size=1, per_device_eval_batch_size=1, warmup_ratio=0.1,
    max_grad_norm=1.0, optim='paged_adamw_8bit', lr_scheduler_type='linear')
LORA = dict(r=8, lora_alpha=16, lora_dropout=0.05, bias='none',
            target_modules='all-linear', task_type='CAUSAL_LM')


def validate_config(config):
    require(config['schema_version'] == 'comparison-training-v1', 'TRAINING_CONFIG_VERSION')
    require(config['model_id'] == MODEL and config['revision'] == REVISION, 'TRAINING_MODEL_PIN')
    require(config['training'] == TRAINING and config['lora'] == LORA, 'TRAINING_RECIPE_CHANGED')
    require(config['seed'] == 42 and config['epochs'] == 1
            and config['counts'] == COUNTS and config['holdout_included'] is False, 'TRAINING_SPLIT_OR_EPOCH')
    require(config['expected_updates'] == math.ceil(COUNTS['train']/4)
            and config['eval_steps'] == 25 and config['save_steps'] == 50, 'TRAINING_SCHEDULE')
    require(config['initialization'] == 'PINNED_BASE_FRESH_LORA'
            and config['selection'] == 'FINAL_EPOCH_NOT_BEST_ON_HOLDOUT'
            and config['main_authorized'] is False, 'TRAINING_BOUNDARY')


def load_package(package):
    from transformers import AutoTokenizer
    package = Path(package).resolve()
    manifest = read_json(package/'manifest.json')
    verify_inventory(package, manifest['files'])
    require(inventory(package, ('manifest.json',)) == manifest['files'], 'TRAINING_PACKAGE_FILE_SET')
    require(not any('holdout' in name.lower() or '/adapter/' in '/'+name for name in manifest['files']), 'FORBIDDEN_TRAINING_PAYLOAD')
    config = read_json(package/'training-config.json')
    validate_config(config)
    reference = read_json(package/'tokenizer-reference.json')
    require(reference['model_id'] == MODEL and reference['revision'] == REVISION, 'TRAINING_TOKENIZER_PIN')
    for name, expected in reference['packages'].items():
        require(version(name) == expected, 'TOKENIZER_LIBRARY_PIN:'+name)
    for name, info in reference['files'].items():
        path = package/'tokenizer'/name
        require(path.stat().st_size == info['size_bytes'] and sha_file(path) == info['sha256'], 'TOKENIZER_BYTES')
    tokenizer = AutoTokenizer.from_pretrained(package/'tokenizer', local_files_only=True, trust_remote_code=False)
    import hashlib
    require(tokenizer.eos_token_id == reference['eos_token_id']
            and tokenizer.pad_token_id == reference['pad_token_id']
            and hashlib.sha256(tokenizer.chat_template.encode()).hexdigest() == reference['chat_template_sha256'], 'TOKENIZER_IDENTITY')
    selection = read_json(package/'data/selection.json')
    require(set(selection['splits']) == set(COUNTS), 'TRAINING_SPLITS')
    data, seen = {}, set()
    for split, count in COUNTS.items():
        payloads = read_rows(package/'data'/(split+'.jsonl'))
        tokens = read_rows(package/'data'/('tokenized-'+split+'.jsonl'))
        require(len(payloads) == len(tokens) == len(selection['splits'][split]) == count, 'TRAINING_COUNT')
        data[split] = []
        for rid, payload, row in zip(selection['splits'][split], payloads, tokens):
            require(rid not in seen and row['record_id'] == rid, 'TRAINING_ID_BINDING')
            seen.add(rid)
            expected = tokenize_payload(payload, tokenizer, config['token_limits'])
            require(row == dict(record_id=rid, **expected), 'TRAINING_TOKEN_MASK_BINDING')
            data[split].append({k: row[k] for k in ('input_ids','attention_mask','labels')})
    return data, tokenizer, config


def arguments(config, output, train_count, mode, *, cpu_test=False):
    from transformers import TrainingArguments
    values = dict(config['training'])
    if cpu_test:
        values['optim'] = 'adamw_torch'
    # max_steps=-1 lets Trainer cover the short final accumulation group once.
    return TrainingArguments(output_dir=str(output), **values, num_train_epochs=1,
        max_steps=2 if mode == 'smoke' else -1, seed=42, data_seed=42,
        eval_strategy='steps', eval_steps=2 if mode == 'smoke' else 25,
        save_strategy='steps', save_steps=2 if mode == 'smoke' else 50,
        save_total_limit=2, load_best_model_at_end=False, save_only_model=False,
        logging_strategy='steps', logging_steps=1, logging_nan_inf_filter=False,
        fp16=not cpu_test, bf16=False, use_cpu=cpu_test,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={'use_reentrant':False},
        report_to='none', remove_unused_columns=False, label_names=['labels'],
        dataloader_num_workers=0, dataloader_pin_memory=not cpu_test,
        disable_tqdm=True, save_safetensors=True)


def fit(model, data, tokenizer, config, output, mode, *, cpu_test=False):
    import torch
    from transformers import Trainer, TrainerCallback
    output = Path(output)
    args = arguments(config, output, len(data['train']), mode, cpu_test=cpu_test)
    require(cpu_test or (args.n_gpu == 1 and args.world_size == 1), 'ONE_T4_NO_DATAPARALLEL')
    expected = 2 if mode == 'smoke' else math.ceil(len(data['train'])/4)
    collator = CompletionCollator(tokenizer.pad_token_id, tokenizer.eos_token_id,
                                 config['token_limits']['max_sequence_tokens'])
    evidence = make_callbacks(output, config)
    class Diagnostics(TrainerCallback):
        started = None
        def on_train_begin(self, args, state, control, **kwargs):
            self.started = time.perf_counter()
        def on_step_end(self, args, state, control, **kwargs):
            elapsed = time.perf_counter()-self.started
            row = dict(step=state.global_step, epoch=state.epoch, elapsed_seconds=elapsed,
                cumulative_updates_per_second=state.global_step/elapsed,
                allocated_bytes=0 if cpu_test else torch.cuda.memory_allocated(),
                reserved_bytes=0 if cpu_test else torch.cuda.memory_reserved(),
                peak_allocated_bytes=0 if cpu_test else torch.cuda.max_memory_allocated(),
                peak_reserved_bytes=0 if cpu_test else torch.cuda.max_memory_reserved())
            with (output/'resource-metrics.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, allow_nan=False)+'\n')
            if state.global_step == expected:
                control.should_evaluate = True
                control.should_save = True
            return control
    trainer = Trainer(model=model, args=args, train_dataset=data['train'], eval_dataset=data['validation'],
        data_collator=collator, callbacks=[evidence, Diagnostics()])
    evidence.trainer = trainer
    write_json(output/'training-arguments.json', args.to_dict())
    # Evaluate the same validation set at step zero and every 25 updates.
    baseline = trainer.evaluate()
    write_json(output/'baseline-evaluation.json', baseline)
    if not cpu_test:
        torch.cuda.reset_peak_memory_stats()
    trainer.train()
    update = evidence.report(model, trainer.state.global_step)
    write_json(output/'adapter-update-report.json', update)
    require(update['global_step'] == expected and update['applied_updates'] == expected
            and update['scaler_skipped_updates'] == 0 and update['finite_gradient_checks'] == expected
            and math.isfinite(update['adapter_delta_l2']) and update['adapter_delta_l2'] > 0, 'EXPANDED_UPDATE_PROOF')
    if mode == 'full':
        require(abs(trainer.state.epoch-1) < 1e-6, 'ONE_EPOCH_COVERAGE')
    evaluation = next(r for r in reversed(trainer.state.log_history)
                      if r.get('step') == expected and 'eval_loss' in r)
    require(math.isfinite(evaluation['eval_loss']), 'NONFINITE_FINAL_EVAL')
    write_json(output/'eval-metrics.json', evaluation)
    trainer.save_model(str(output/'final-adapter'))
    trainer.save_state()
    require((output/('checkpoint-'+str(expected))/'optimizer.pt').is_file(), 'FINAL_CHECKPOINT_OPTIMIZER_MISSING')
    return update


def train(package, output, mode, cache_dir):
    import torch
    from transformers import set_seed
    package = Path(package).resolve()
    output = output_guard(output, [package])
    data, tokenizer, config = load_package(package)
    require(mode in ('smoke','full'), 'TRAINING_MODE')
    output.mkdir(parents=True)
    status, error = 'FAILED', None
    def phase(value):
        write_json(output/'phase.json', dict(phase=value, mode=mode))
    try:
        write_json(output/'resolved-config.json', config)
        write_json(output/'package-binding.json', dict(package_manifest_sha256=sha_file(package/'manifest.json'),
            source_training_manifest_sha256=config['data_manifest_sha256'], mode=mode,
            counts=COUNTS, holdout_included=False, initialization='PINNED_BASE_FRESH_LORA'))
        source = output/'source'
        source.mkdir()
        for path in sorted(package.glob('scripts/**/*.py')):
            target = source/path.relative_to(package)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
        with (output/'stdout.txt').open('x',encoding='utf-8') as stdout, \
             (output/'stderr.txt').open('x',encoding='utf-8') as stderr, \
             redirect_stdout(stdout), redirect_stderr(stderr):
            phase('CHECKING_ENVIRONMENT_AND_STORAGE')
            write_json(output/'environment.json', snapshot(config))
            budget = check_training_storage(config, cache_dir, output, allow_download=True)
            # Two retained checkpoints, final adapter, charts, ZIP and export headroom.
            import shutil
            required_output = 4*1024**3 + (budget['cache_required_bytes'] if budget['shared_volume'] else 0)
            require(budget['passed'] and shutil.disk_usage(output).free >= required_output,
                    'TRAINING_STORAGE_HEADROOM')
            write_json(output/'storage.json', budget)
            set_seed(42)
            phase('LOADING_PINNED_BASE_FRESH_LORA')
            model = load_training_model(config, allow_download=True, cache_dir=cache_dir)
            require(all(torch.count_nonzero(p).item() == 0 for n,p in model.named_parameters() if 'lora_B' in n),
                    'FRESH_LORA_B_NOT_ZERO')
            write_json(output/'parameter-report.json', parameter_report(model))
            phase('BASELINE_VALIDATION')
            fit(model, data, tokenizer, config, output, mode)
            phase('RENDERING_TRAINING_CHARTS')
            from scripts.comparison.training_report import render
            render(output, output/'figures')
            status = 'TRAINING_COMPLETED'
            phase(status)
    except BaseException as exc:
        error = dict(type=type(exc).__name__, message=str(exc))
        write_json(output/'failure.json', error)
        phase('FAILED')
        raise
    finally:
        write_json(output/'run-manifest.json', dict(status=status, mode=mode,
            config_sha256=digest(config), package_manifest_sha256=sha_file(package/'manifest.json'),
            source_training_manifest_sha256=config['data_manifest_sha256'], error=error,
            files=inventory(output, ('run-manifest.json',))))
    print(status+': '+str(output), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('smoke','full'), default='smoke')
    parser.add_argument('--cache-dir', type=Path, default=Path.home()/'.cache/huggingface/hub')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    os.environ.update(USE_TF='0', USE_FLAX='0', CUDA_VISIBLE_DEVICES='0', WANDB_DISABLED='true', TOKENIZERS_PARALLELISM='false')
    if args.check_only:
        data, _, config = load_package(args.package)
        print(json.dumps(dict(status='TRAINING_INPUTS_READY_GPU_NOT_RUN', counts={k:len(v) for k,v in data.items()}, expected_updates=config['expected_updates'])))
    else:
        train(args.package, args.output, args.mode, args.cache_dir)
