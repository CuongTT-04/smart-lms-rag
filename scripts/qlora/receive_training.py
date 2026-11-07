"""Recompute received GPU evidence on CPU; this does not rerun GPU operations."""
import argparse
import json
import math
from pathlib import Path, PurePosixPath
import torch
from safetensors.torch import load_file
from scripts.qlora.data import read_json, read_rows, sha_file, require, digest
from scripts.qlora.pilot import audit as audit_pilot
from scripts.qlora.smoke import audit as audit_smoke
from scripts.qlora.assessment import cases_from_bundle, score_generation, summarize, check_run, PILOT_SHA, GENERATION
from scripts.qlora.runtime import verify_inventory, inventory, write_json


def verify_resume_binding(pilot, resume):
    """Bind resumed settings and measure the update independently of report text."""
    pilot, resume = Path(pilot), Path(resume)
    original = read_json(pilot / 'run-manifest.json')
    current = read_json(resume / 'run-manifest.json')
    config = read_json(pilot / 'resolved-config.json')
    require(read_json(resume / 'resolved-config.json') == config
            and digest(config) == original['config_sha256'] == current['config_sha256']
            and current['data_manifest_sha256'] == original['data_manifest_sha256'], 'RESUME_CONFIG_BINDING')
    ignored = {'output_dir', 'logging_dir'}
    settings = [{k:v for k,v in read_json(folder / 'training-arguments.json').items() if k not in ignored}
                for folder in (pilot, resume)]
    require(settings[0] == settings[1] and settings[1]['max_steps'] == 50, 'RESUME_ARGUMENTS_DRIFT')
    references = [{k:v for k,v in read_json(folder / 'data-reference.json').items()
                   if k not in {'resume_checkpoint', 'resume_manifest_sha256'}} for folder in (pilot, resume)]
    require(references[0] == references[1], 'RESUME_DATA_REFERENCE_DRIFT')
    for folder, step in ((pilot, 25), (resume, 26)):
        require(read_json(folder / f'checkpoint-{step}/binding.json') == dict(
            config_sha256=original['config_sha256'], data_manifest_sha256=original['data_manifest_sha256'],
            global_step=step), 'RESUME_CHECKPOINT_BINDING')
    configs = [read_json(folder / f'checkpoint-{step}/adapter_config.json')
               for folder, step in ((pilot, 25), (resume, 26))]
    for cfg in configs:
        if isinstance(cfg.get('target_modules'), list):
            cfg['target_modules'] = sorted(cfg['target_modules'])
    require(configs[0] == configs[1], 'RESUME_ADAPTER_CONFIG')
    before = load_file(pilot / 'checkpoint-25/adapter_model.safetensors')
    after = load_file(resume / 'checkpoint-26/adapter_model.safetensors')
    require(before and set(before) == set(after), 'RESUME_TENSOR_KEYS')
    squared, changed = 0.0, 0
    for name, value in before.items():
        target = after[name]
        require(value.shape == target.shape and value.dtype == target.dtype
                and torch.isfinite(value).all().item() and torch.isfinite(target).all().item(), 'RESUME_TENSOR_SHAPE_FINITE')
        changed += int(not torch.equal(value, target))
        squared += (target.double() - value.double()).square().sum().item()
    delta = math.sqrt(squared)
    require(changed > 0 and math.isfinite(delta) and delta > 0, 'RESUME_ACTUAL_UPDATE')
    reported = read_json(resume / 'adapter-update-report.json')['adapter_delta_l2']
    require(math.isfinite(reported) and math.isclose(delta, reported, rel_tol=1e-5, abs_tol=1e-8), 'RESUME_DELTA_RECOMPUTATION')
    return dict(changed_tensors=changed, adapter_delta_l2=delta)



def verify_resume_parent(binding, context):
    # Kaggle may mount the authenticated pilot directly at a dataset root.
    # Bind to the recorded remote location, not the receiver's folder name.
    parent = PurePosixPath(context['pilot'].replace('\\', '/'))
    checkpoint = PurePosixPath(binding['resume_checkpoint'].replace('\\', '/'))
    require(parent.is_absolute() and '..' not in parent.parts and '..' not in checkpoint.parts
            and binding['resume_manifest_sha256'] == context['pilot_manifest_sha256'] == PILOT_SHA
            and checkpoint == parent / 'checkpoint-25', 'RESUME_PARENT')


def audit_training(smoke, pilot, verification, bundle, report):
    smoke, pilot, verification, bundle, report = map(Path, (smoke, pilot, verification, bundle, report))
    require(not report.exists(), 'REPORT_EXISTS')
    torch.set_num_threads(2)
    reports=dict(smoke=audit_smoke(smoke),pilot=audit_pilot(pilot))
    manifest=read_json(verification/'manifest.json')
    verify_inventory(verification,manifest['files'])
    require(set(inventory(verification,('manifest.json',)))==set(manifest['files']),'VERIFY_FILE_SET')
    context=read_json(verification/'context.json')
    require(context['pilot_manifest_sha256']==PILOT_SHA==sha_file(pilot/'run-manifest.json'),'PILOT_RECEIPT')
    config=read_json(pilot/'resolved-config.json')
    require(context['config_sha256']==digest(config),'CONFIG_BINDING')
    cases=cases_from_bundle(bundle,config)
    require(read_json(verification/'evaluation/cases.json')==cases,'EVAL_CASES_BOUND')
    require(read_json(verification/'evaluation/generation-config.json')==GENERATION,'EVAL_CONFIG_BOUND')
    predictions=read_rows(verification/'evaluation/predictions.jsonl')
    require(len(predictions)==40 and len({(r['record_id'],r['arm']) for r in predictions})==40,'OUTPUT_COUNT')
    for row in predictions:
        case=next(c for c in cases if c['record_id']==row['record_id'])
        require(row['prompt_sha256']==digest(case['prompt']),'EVAL_PROMPT')
        require(row['checks']==score_generation(row['raw_output'],case,row['status']),'OUTPUT_RECOMPUTATION')
    require(summarize(predictions)==read_json(verification/'evaluation/comparison.json'),'METRICS_RECOMPUTATION')
    reload=read_json(verification/'evaluation/reload.json')
    require(reload['adapter_sha256']==sha_file(pilot/'final-adapter/adapter_model.safetensors')
            and reload['reloaded_saved_tensors_exact'] is True and reload['requires_grad_any'] is False,'RELOAD_BINDING')
    resume=verification/'resume'
    resume_manifest=read_json(resume/'run-manifest.json')
    check_run(resume,sha_file(resume/'run-manifest.json'))
    require(resume_manifest['source_files_sha256']==read_json(pilot/'run-manifest.json')['source_files_sha256'],'RESUME_SOURCE_IDENTITY')
    measured_update = verify_resume_binding(pilot, resume)
    binding=read_json(resume/'data-reference.json')
    verify_resume_parent(binding, context)
    require(read_json(resume/'training-arguments.json')['max_steps']==50,'RESUME_SCHEDULE')
    require(read_json(resume/'checkpoint-26/trainer_state.json')['global_step']==26,'RESUME_GLOBAL_STEP')
    before=torch.load(pilot/'checkpoint-25/scheduler.pt',map_location='cpu',weights_only=True)
    after=torch.load(resume/'checkpoint-26/scheduler.pt',map_location='cpu',weights_only=True)
    require(before['last_epoch']==25 and after['last_epoch']==26 and before['base_lrs']==after['base_lrs'],'SCHEDULER_RESTORE')
    optimizer_steps=[]
    for path,expected in [(pilot/'checkpoint-25/optimizer.pt',25),(resume/'checkpoint-26/optimizer.pt',26)]:
        state=torch.load(path,map_location='cpu',weights_only=True)
        steps={int(v['step']) for v in state['state'].values()}
        require(steps=={expected},'OPTIMIZER_RESTORE')
        optimizer_steps.append(expected)
        del state
    update=read_json(resume/'adapter-update-report.json')
    require((update['start_global_step'],update['global_step'],update['applied_updates'],update['scaler_skipped_updates'])==(25,26,1,0)
            and update['adapter_delta_l2']>0 and update['base_frozen'] is True,'RESUME_UPDATE')
    final=load_file(resume/'final-adapter/adapter_model.safetensors')
    saved=load_file(resume/'checkpoint-26/adapter_model.safetensors')
    require(set(final)==set(saved) and all(torch.equal(value,saved[key]) and torch.isfinite(value).all() for key,value in final.items()),'RESUME_TENSORS')
    reports.update(verification=dict(passed=True, archived_gpu_reload=reload, optimizer_steps=optimizer_steps,
        resume_global_step=26, measured_update=measured_update, predictions_checked=40, comparison=summarize(predictions)),
        receiver_scope='INDEPENDENT_CPU_AUDIT_OF_AUTHENTICATED_GPU_ARTIFACTS',
        receiver_cuda_available=torch.cuda.is_available(),receiver_reexecuted_gpu_reload=False,
        receiver_reexecuted_gpu_resume=False,human_peer_approval_created=False,
        technical_milestone='SMALL_QLORA_CONFIG_CHECKPOINT_LOG_VERIFIED')
    write_json(report, reports)
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('smoke', 'pilot', 'verification', 'bundle', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    audit_training(**vars(args))
    print('CPU_RECEIVER_TRAINING_ARTIFACT_AUDIT_PASSED: ' + str(args.report))


if __name__ == '__main__':
    main()
