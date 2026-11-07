"""Trainer setup, update evidence and authenticated resume, independent of serving."""
from datetime import datetime, timezone
from importlib.metadata import distributions, version
import json
import math
import platform
from pathlib import Path
import subprocess
import sys
import time

from .data import digest, read_json, require, sha_file, within


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')


def inventory(folder, excluded=()):
    folder = Path(folder).resolve()
    result = {}
    for path in sorted(folder.rglob('*')):
        require(not path.is_symlink(), 'ARTIFACT_SYMLINK')
        if path.is_file() and path.relative_to(folder).as_posix() not in excluded:
            result[path.relative_to(folder).as_posix()] = {
                'sha256': sha_file(path), 'size_bytes': path.stat().st_size}
    return result


def verify_inventory(folder, files):
    for name, info in files.items():
        path = within(folder, name)
        require(path.is_file() and path.stat().st_size == info['size_bytes']
                and sha_file(path) == info['sha256'], 'ARTIFACT_INTEGRITY:' + name)


def validate_recipe(config, profile):
    require(config['schema_version'] == 'ohayo-qlora-recipe-v1', 'RECIPE_VERSION')
    require(profile in ('smoke', 'pilot'), 'PROFILE')
    require(config['profiles'] == {
        'smoke': {'max_steps': 2, 'save_steps': 2, 'eval_steps': 2},
        'pilot': {'max_steps': 50, 'save_steps': 25, 'eval_steps': 25}}, 'STEP_PROFILES')
    train = config['training']
    require(train['per_device_train_batch_size'] == train['per_device_eval_batch_size'] == 1
            and train['gradient_accumulation_steps'] == 4, 'BATCH_RECIPE')
    require(all(isinstance(train[k], (float, int)) and not isinstance(train[k], bool)
                and math.isfinite(train[k]) and train[k] > 0
                for k in ('learning_rate', 'max_grad_norm'))
            and 0 <= train['warmup_ratio'] <= 1, 'OPTIMIZER_RECIPE')
    require(config['seed'] == 42 and config['lora'] == {
        'r': 8, 'lora_alpha': 16, 'lora_dropout': 0.05, 'bias': 'none',
        'target_modules': 'all-linear', 'task_type': 'CAUSAL_LM'}, 'LORA_RECIPE')


def output_guard(output, inputs):
    output = Path(output).resolve()
    require(not output.exists(), 'OUTPUT_ALREADY_EXISTS')
    for value in inputs:
        value = Path(value).resolve()
        require(not output.is_relative_to(value) and not value.is_relative_to(output),
                'OUTPUT_OVERLAPS_INPUT')
    return output


def training_arguments(config, profile, output, *, cpu_test=False):
    from transformers import TrainingArguments
    values = dict(config['training'])
    args = TrainingArguments(
        output_dir=str(output), **values, **config['profiles'][profile],
        seed=config['seed'], data_seed=config['seed'],
        eval_strategy='steps', save_strategy='steps', logging_strategy='steps', logging_steps=1,
        save_total_limit=2, save_only_model=False, load_best_model_at_end=False,
        fp16=not cpu_test, bf16=False, use_cpu=cpu_test,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={'use_reentrant': False},
        report_to='none', remove_unused_columns=False, label_names=['labels'],
        dataloader_num_workers=0, dataloader_pin_memory=not cpu_test,
        disable_tqdm=True, save_safetensors=True, logging_nan_inf_filter=False)
    if not cpu_test:
        require(args.n_gpu == 1 and args.world_size == 1, 'SINGLE_VISIBLE_GPU_REQUIRED_NO_DATAPARALLEL')
    return args


def adapter_parameters(model):
    selected = {}
    for name, param in model.named_parameters():
        if param.requires_grad:
            require('lora_' in name, 'BASE_PARAMETER_TRAINABLE:' + name)
            selected[name] = param
    require(bool(selected), 'NO_TRAINABLE_ADAPTER')
    return selected


def parameter_report(model):
    selected = adapter_parameters(model)
    return dict(trainable_parameters=sum(p.numel() for p in selected.values()),
                total_parameter_elements=sum(p.numel() for p in model.parameters()),
                trainable_names=sorted(selected), base_frozen=True,
                note='Quantized parameter elements are storage counts, not dense base parameter counts.')


def resume_checkpoint(checkpoint, expected_manifest_sha256, config, stop_after_step):
    checkpoint = Path(checkpoint).resolve()
    parent = checkpoint.parent
    require(expected_manifest_sha256 is not None, 'RESUME_RECEIPT_REQUIRED')
    require(sha_file(parent / 'run-manifest.json') == expected_manifest_sha256,
            'RESUME_MANIFEST_HASH')
    report = read_json(parent / 'run-manifest.json')
    require(report['status'] == 'TRAINING_COMPLETED' and report['profile'] == 'pilot'
            and report['config_sha256'] == digest(config), 'RESUME_RUN_IDENTITY')
    verify_inventory(parent, report['files'])
    require(set(inventory(parent, ('run-manifest.json', 'SHA256SUMS.txt')))
            == set(report['files']), 'RESUME_EXTRA_FILES')
    code = {p.name: sha_file(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    require(report['source_files_sha256'] == code, 'RESUME_TRAINER_CODE_CHANGED')
    require(checkpoint.name == 'checkpoint-25' and checkpoint.is_dir(), 'RESUME_STEP_25_REQUIRED')
    binding = read_json(checkpoint / 'binding.json')
    require(binding['config_sha256'] == digest(config)
            and binding['data_manifest_sha256'] == config['data_manifest_sha256'], 'RESUME_BINDING')
    require(read_json(checkpoint / 'trainer_state.json')['global_step'] == 25,
            'RESUME_STATE_STEP')
    required = {'adapter_config.json', 'adapter_model.safetensors', 'trainer_state.json',
                'optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'scaler.pt'}
    require(required <= {p.name for p in checkpoint.iterdir()}, 'INCOMPLETE_RESUME_STATE')
    require(stop_after_step == 26, 'RESUME_STOP_26_REQUIRED')
    return checkpoint


def make_callbacks(output, config, *, stop_after_step=None):
    import torch
    from transformers import TrainerCallback

    class EvidenceCallback(TrainerCallback):
        trainer = None

        def __init__(self):
            self.before = {}
            self.applied = 0
            self.skipped = 0
            self.gradient_checks = 0
            self.started = None
            self.start_step = None

        def on_train_begin(self, args, state, control, model=None, **kwargs):
            self.started = time.monotonic()
            self.start_step = state.global_step
            self.before = {n: p.detach().float().cpu().clone()
                           for n, p in adapter_parameters(model).items()}

        def on_pre_optimizer_step(self, args, state, control, model=None, **kwargs):
            gradients = [p.grad for p in adapter_parameters(model).values() if p.grad is not None]
            require(bool(gradients), 'NO_ADAPTER_GRADIENT')
            require(all(torch.isfinite(g).all().item() for g in gradients), 'NONFINITE_GRADIENT')
            self.gradient_checks += 1

        def on_step_end(self, args, state, control, **kwargs):
            skipped = bool(self.trainer.accelerator.optimizer_step_was_skipped)
            self.skipped += int(skipped)
            self.applied += int(not skipped)
            event = dict(step=state.global_step, update_applied=not skipped,
                         elapsed_seconds=time.monotonic() - self.started)
            with (output / 'optimizer-events.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(event, allow_nan=False) + '\n')
            write_json(output / 'phase.json', dict(phase='TRAINING_AND_VALIDATION', **event))
            if stop_after_step is not None and state.global_step >= stop_after_step:
                control.should_training_stop = True
                control.should_save = True
                control.should_evaluate = True
            return control

        def on_log(self, args, state, control, logs=None, **kwargs):
            logs = dict(logs or {})
            for value in logs.values():
                if isinstance(value, (int, float)):
                    require(math.isfinite(value), 'NONFINITE_TRAINING_LOG')
            with (output / 'train-metrics.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(dict(step=state.global_step, **logs), allow_nan=False) + '\n')

        def on_save(self, args, state, control, **kwargs):
            checkpoint = output / ('checkpoint-' + str(state.global_step))
            write_json(checkpoint / 'binding.json', {
                'config_sha256': digest(config), 'data_manifest_sha256': config['data_manifest_sha256'],
                'global_step': state.global_step})

        def report(self, model, global_step):
            after = adapter_parameters(model)
            require(set(after) == set(self.before), 'ADAPTER_PARAMETERS_CHANGED')
            squared = sum((p.detach().float().cpu() - self.before[n]).double().square().sum().item()
                          for n, p in after.items())
            return dict(start_global_step=self.start_step, global_step=global_step,
                        attempted_updates=self.applied + self.skipped,
                        applied_updates=self.applied, scaler_skipped_updates=self.skipped,
                        finite_gradient_checks=self.gradient_checks,
                        adapter_delta_l2=math.sqrt(squared), base_frozen=True)

    return EvidenceCallback()


def fit(model, data, collator, args, output, config, *, resume=None, stop_after_step=None):
    from transformers import Trainer
    if not args.use_cpu:
        require(args.n_gpu == 1 and args.world_size == 1, 'SINGLE_VISIBLE_GPU_REQUIRED_NO_DATAPARALLEL')
    evidence = make_callbacks(output, config, stop_after_step=stop_after_step)
    trainer = Trainer(model=model, args=args, train_dataset=data['train'],
                      eval_dataset=data['validation'], data_collator=collator,
                      callbacks=[evidence])
    evidence.trainer = trainer
    try:
        trainer.train(resume_from_checkpoint=str(resume) if resume else None)
    except BaseException as exc:
        # A CUDA failure can poison the context. Do not copy tensors back to CPU
        # while handling it, or replace the original exception with a second one.
        failure = dict(error_type=type(exc).__name__, error=str(exc),
                       global_step=trainer.state.global_step,
                       observed_applied_updates=evidence.applied,
                       observed_skipped_updates=evidence.skipped,
                       adapter_delta_l2=None, tensor_measurement='NOT_ATTEMPTED_ON_FAILED_RUN')
        try:
            write_json(output / 'training-failure.json', failure)
        except OSError:
            pass
        raise
    update = evidence.report(model, trainer.state.global_step)
    write_json(output / 'adapter-update-report.json', update)
    target = stop_after_step or args.max_steps
    require(trainer.state.global_step == target and update['applied_updates'] > 0
            and update['scaler_skipped_updates'] == 0
            and update['attempted_updates'] == target - update['start_global_step']
            and update['finite_gradient_checks'] == update['attempted_updates']
            and math.isfinite(update['adapter_delta_l2']) and update['adapter_delta_l2'] > 0,
            'OPTIMIZER_UPDATE_PROOF_FAILED')
    metrics = next((entry for entry in reversed(trainer.state.log_history)
                    if entry.get('step') == trainer.state.global_step and 'eval_loss' in entry), None)
    if metrics is None:
        metrics = trainer.evaluate()
    require(math.isfinite(metrics['eval_loss']), 'NONFINITE_EVAL_LOSS')
    write_json(output / 'eval-metrics.json', metrics)
    trainer.save_model(str(output / 'final-adapter'))
    trainer.save_state()
    return trainer, update


def environment():
    import torch
    return dict(python=sys.version, platform=platform.platform(), torch=torch.__version__,
                cuda=torch.version.cuda, cuda_available=torch.cuda.is_available(),
                gpus=[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
                dependencies={d.metadata['Name']: d.version for d in distributions()},
                recorded_at=datetime.now(timezone.utc).isoformat())


def load_training_model(config, *, allow_download=False, cache_dir=None):
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    require(torch.cuda.is_available(), 'CUDA_REQUIRED')
    require(torch.cuda.device_count() == 1, 'SINGLE_VISIBLE_GPU_REQUIRED_NO_DATAPARALLEL')
    require('T4' in torch.cuda.get_device_name(0), 'PROFILE_REQUIRES_T4')
    require(not torch.distributed.is_initialized(), 'SINGLE_PROCESS_ONLY')
    free, total = torch.cuda.mem_get_info(0)
    require(free >= 12 * 1024 ** 3, 'GPU_BUSY_OR_INSUFFICIENT_FREE_VRAM')
    for name, expected in config['dependencies'].items():
        require(version(name) == expected, 'DEPENDENCY_VERSION:' + name)
    quantization = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                                      bnb_4bit_use_double_quant=True,
                                      bnb_4bit_compute_dtype=torch.float16)
    model = AutoModelForCausalLM.from_pretrained(
        config['model_id'], revision=config['revision'], trust_remote_code=False,
        local_files_only=not allow_download, quantization_config=quantization,
        torch_dtype=torch.float16, device_map={'': 0}, attn_implementation='sdpa',
        use_safetensors=True, cache_dir=str(cache_dir) if cache_dir is not None else None)
    require(model.config._commit_hash == config['revision'], 'BASE_REVISION_MISMATCH')
    require(getattr(model, 'is_loaded_in_4bit', False), 'BASE_NOT_4BIT')
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                            gradient_checkpointing_kwargs={'use_reentrant': False})
    model = get_peft_model(model, LoraConfig(**config['lora'], revision=config['revision']))
    adapter_parameters(model)
    return model


def finish_manifest(output, *, status, profile, config, error_type=None):
    source = Path(__file__).parent
    code = {p.name: sha_file(p) for p in sorted(source.glob('*.py'))}
    try:
        git = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                             check=True, cwd=source).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        git = None
    manifest = dict(status=status, profile=profile, config_sha256=digest(config),
                    data_manifest_sha256=config['data_manifest_sha256'],
                    source_files_sha256=code, git_head=git,
                    note='Source file hashes identify uncommitted code; git_head alone does not.',
                    error_type=error_type,
                    files=inventory(output, ('run-manifest.json', 'SHA256SUMS.txt')))
    write_json(output / 'run-manifest.json', manifest)
    files = inventory(output, ('SHA256SUMS.txt',))
    (output / 'SHA256SUMS.txt').write_text(''.join(
        info['sha256'] + '  ' + name + '\n' for name, info in files.items()), encoding='utf-8')
