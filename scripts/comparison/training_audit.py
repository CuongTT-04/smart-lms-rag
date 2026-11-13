"""Audit expanded training and export evidence; never execute serialized optimizer state."""
import argparse
import math
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile

from scripts.comparison.protocol import write_json
from scripts.comparison.training import validate_config
from scripts.comparison.training_report import FIGURES, series
from scripts.comparison.training_environment import verify as verify_environment
from scripts.qlora.data import digest, read_json, read_rows, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory


def audit(run, package):
    from safetensors import safe_open
    import torch
    run, package = Path(run).resolve(), Path(package).resolve()
    package_manifest = read_json(package/'manifest.json')
    verify_inventory(package,package_manifest['files'])
    require(inventory(package,('manifest.json',)) == package_manifest['files'], 'TRAINING_PACKAGE_FILE_SET')
    manifest = read_json(run/'run-manifest.json')
    verify_inventory(run,manifest['files'])
    require(inventory(run,('run-manifest.json',)) == manifest['files'], 'TRAINING_RUN_FILE_SET')
    require(manifest['status'] == 'TRAINING_COMPLETED', 'TRAINING_NOT_COMPLETED')
    config = read_json(run/'resolved-config.json')
    validate_config(config)
    require(config == read_json(package/'training-config.json')
            and manifest['config_sha256'] == digest(config)
            and manifest['package_manifest_sha256'] == sha_file(package/'manifest.json'), 'TRAINING_CONFIG_BINDING')
    env = read_json(run/'environment.json')
    require(env['cuda_available'] is True and len(env['gpus']) == 1 and 'T4' in env['gpus'][0], 'TRAINING_GPU_EVIDENCE')
    environment_check = verify_environment(run, package, config, env)
    mode = manifest['mode']
    require(mode in ('smoke','full'), 'TRAINING_RUN_MODE')
    expected = 2 if mode == 'smoke' else config['expected_updates']
    update = read_json(run/'adapter-update-report.json')
    require(update['global_step'] == update['applied_updates'] == update['attempted_updates'] == expected
            and update['start_global_step'] == 0 and update['scaler_skipped_updates'] == 0
            and update['finite_gradient_checks'] == expected and update['base_frozen'] is True
            and math.isfinite(update['adapter_delta_l2']) and update['adapter_delta_l2'] > 0, 'TRAINING_UPDATE_EVIDENCE')
    events = read_rows(run/'optimizer-events.jsonl')
    require([r['step'] for r in events] == list(range(1,expected+1))
            and all(r['update_applied'] for r in events), 'TRAINING_EVENT_COVERAGE')
    train, evaluation, resources = series(run)
    require(len(train) == expected, 'TRAINING_LOG_COUNT')
    expected_evals = [0,2] if mode == 'smoke' else [0]+list(range(25,expected,25))+[expected]
    require([r['step'] for r in evaluation] == expected_evals, 'TRAINING_EVAL_SCHEDULE')
    require(evaluation[0]['eval_loss'] == read_json(run/'baseline-evaluation.json')['eval_loss']
            and evaluation[-1]['eval_loss'] == read_json(run/'eval-metrics.json')['eval_loss'], 'TRAINING_EVAL_BINDING')
    args = read_json(run/'training-arguments.json')
    require(args['max_steps'] == (2 if mode == 'smoke' else -1)
            and args['num_train_epochs'] == 1 and args['gradient_accumulation_steps'] == 4
            and args['fp16'] is True and args['bf16'] is False
            and args['load_best_model_at_end'] is False
            and all(args[k] == v for k,v in config['training'].items()), 'TRAINING_ARGUMENTS_CHANGED')
    state = read_json(run/'trainer_state.json')
    require(state['global_step'] == expected and (mode != 'full' or abs(state['epoch']-1)<1e-6), 'TRAINING_ONE_EPOCH')
    checkpoint_steps = [2] if mode == 'smoke' else [150,193]
    require({p.name for p in run.glob('checkpoint-*')} == {'checkpoint-'+str(s) for s in checkpoint_steps}, 'TRAINING_CHECKPOINT_SET')
    for step in checkpoint_steps:
        checkpoint = run/('checkpoint-'+str(step))
        require({'adapter_config.json','adapter_model.safetensors','trainer_state.json','optimizer.pt',
                 'scheduler.pt','rng_state.pth','scaler.pt','binding.json'} <= {p.name for p in checkpoint.iterdir()}, 'TRAINING_CHECKPOINT_INCOMPLETE')
        binding = read_json(checkpoint/'binding.json')
        require(binding == dict(config_sha256=digest(config),data_manifest_sha256=config['data_manifest_sha256'],global_step=step), 'TRAINING_CHECKPOINT_BINDING')
    adapter = run/'final-adapter'
    settings = read_json(adapter/'adapter_config.json')
    require(settings['base_model_name_or_path'] == config['model_id'] and settings['revision'] == config['revision']
            and all(settings[k] == config['lora'][k] for k in ('r','lora_alpha','lora_dropout','bias','task_type')), 'TRAINING_ADAPTER_CONFIG')
    parameters = read_json(run/'parameter-report.json')
    require(parameters['base_frozen'] is True and parameters['trainable_parameters'] == 20185088, 'TRAINING_PARAMETER_COUNT')
    with safe_open(adapter/'adapter_model.safetensors',framework='pt',device='cpu') as tensors:
        require(len(tensors.keys()) == 392 and all('lora_' in k and torch.isfinite(tensors.get_tensor(k)).all().item()
                for k in tensors.keys()), 'TRAINING_ADAPTER_TENSORS')
    adapter_sha = sha_file(adapter/'adapter_model.safetensors')
    require(adapter_sha != config['original_pilot_sha256']
            and adapter_sha == sha_file(run/('checkpoint-'+str(expected))/'adapter_model.safetensors'), 'TRAINING_FINAL_ADAPTER_BYTES')
    for name in FIGURES:
        require((run/'figures'/name).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'), 'TRAINING_FIGURE_MISSING')
    return dict(status='EXPANDED_TRAINING_SMOKE_PASSED' if mode == 'smoke' else 'EXPANDED_ONE_EPOCH_TRAINING_PASSED',
        global_step=expected,epochs=state['epoch'],applied_updates=update['applied_updates'],
        scaler_skipped_updates=0,adapter_delta_l2=update['adapter_delta_l2'],
        adapter_sha256=adapter_sha,train=770,validation=114,holdout_included=False,
        validation_baseline=evaluation[0]['eval_loss'],validation_final=evaluation[-1]['eval_loss'],
        checkpoints=checkpoint_steps,figures=list(FIGURES),
        run_manifest_sha256=sha_file(run/'run-manifest.json'),
        package_manifest_sha256=sha_file(package/'manifest.json'),
        peak_allocated_gib=max(r['peak_allocated_bytes'] for r in resources)/2**30,
        environment_check=environment_check,
        quality_improvement='NOT_ESTABLISHED_PENDING_DEV_COMPARISON',
        independent_resume='NOT_RUN',main_authorized=False)


def dev_package(run, package, output):
    from scripts.comparison.runner import audit_assets, validate_inputs
    report = audit(run,package)
    require(report['status'] == 'EXPANDED_ONE_EPOCH_TRAINING_PASSED', 'FULL_RUN_REQUIRED')
    require(not output.exists() and not output.resolve().is_relative_to(run.resolve()), 'NEW_DEV_PACKAGE_REQUIRED')
    contents = output
    contents.mkdir(parents=True)
    for parent in ('scripts','tokenizer','inputs'):
        shutil.copytree(package/parent,contents/parent)
    shutil.copytree(package/'data/comparison',contents/'data/comparison')
    shutil.copyfile(package/'tokenizer-reference.json',contents/'tokenizer-reference.json')
    (contents/'adapter').mkdir()
    for name in ('adapter_config.json','adapter_model.safetensors'):
        shutil.copyfile(run/'final-adapter'/name,contents/'adapter'/name)
    config = read_json(package/'dev-config-template.json')
    config.update(adapter_sha256=report['adapter_sha256'],
        adapter_config_sha256=sha_file(contents/'adapter/adapter_config.json'),
        selected_adapter='expanded_final_epoch',training_run_manifest_sha256=report['run_manifest_sha256'])
    write_json(contents/'run-config.json',config)
    write_json(contents/'manifest.json',dict(files=inventory(contents)))
    tokenizer,_ = audit_assets(contents,config)
    validate_inputs(*[read_rows(contents/'inputs'/('dev.'+n+'.jsonl')) for n in ('inputs','cache','model-inputs')],tokenizer)
    return report


def export(run, package):
    report = audit(run,package)
    target = run.with_name(run.name+'-audit.json')
    archive = run.with_suffix('.zip')
    receipt = run.with_name(run.name+'-receipt.json')
    require(not any(p.exists() for p in (target,archive,receipt)), 'TRAINING_EXPORT_EXISTS')
    write_json(target,report)
    with ZipFile(archive,'x',compression=ZIP_DEFLATED) as zipped:
        for path in sorted(run.rglob('*')):
            if path.is_file():
                zipped.write(path,path.relative_to(run).as_posix())
    write_json(receipt,dict(archive=archive.name,sha256=sha_file(archive),size_bytes=archive.stat().st_size,
        audit_sha256=sha_file(target),run_manifest_sha256=report['run_manifest_sha256'],base_weights_included=False))
    print(report['status'],flush=True)
    print('ZIP:',archive,'\nReceipt:',receipt,'\nAudit:',target,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--dev-package',type=Path)
    args=parser.parse_args()
    if args.dev_package:
        dev_package(args.run,args.package,args.dev_package)
    else:
        export(args.run,args.package)
