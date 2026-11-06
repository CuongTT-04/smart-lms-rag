"""Private development comparison and authenticated pilot reload/resume evidence."""
import argparse
from collections import Counter
from contextlib import nullcontext
import csv
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import time
import unicodedata
from zipfile import ZIP_DEFLATED, ZipFile

from .data import (authenticate, digest, load_pilot, loads, read_json, read_rows,
                   require, sha_file, within)
from .pilot import audit as audit_pilot
from .runtime import environment, inventory, load_training_model, verify_inventory, write_json


PILOT_NAME = 'pilot-20261104T180615021055Z'
PILOT_SHA = 'b228645e1df2d4370715539399f388208d1c7aa04745ce85ca7ccb94425a2a1d'
ZIP_SHA = 'd7ae6f75c8620bc1463b91ca32fe9fca98b89e261c7e4cc5611736560acd215f'
GENERATION = dict(max_new_tokens=512, do_sample=False, num_beams=1, use_cache=True,
                  eos_token_id=151645, pad_token_id=151643, max_time=90.0)


def check_run(folder, manifest_sha):
    folder = Path(folder).resolve()
    require(sha_file(folder / 'run-manifest.json') == manifest_sha, 'RUN_MANIFEST_IDENTITY')
    manifest = read_json(folder / 'run-manifest.json')
    verify_inventory(folder, manifest['files'])
    require(set(inventory(folder, ('run-manifest.json', 'SHA256SUMS.txt'))) == set(manifest['files']),
            'UNLISTED_RUN_FILES')
    return manifest


def find_pilot(work, search):
    direct = Path(work) / 'runs' / PILOT_NAME
    if (direct / 'run-manifest.json').is_file():
        check_run(direct, PILOT_SHA)
        return direct.resolve()
    candidates = [p.parent for p in Path(search).rglob('run-manifest.json')
                  if sha_file(p) == PILOT_SHA]
    if candidates:
        require(len(candidates) == 1, 'MULTIPLE_PILOT_COPIES_SELECT_EXPLICITLY')
        check_run(candidates[0], PILOT_SHA)
        return candidates[0].resolve()
    archives = [p for p in Path(search).rglob(PILOT_NAME + '.zip') if sha_file(p) == ZIP_SHA]
    require(len(archives) == 1, 'PILOT_MISSING_ADD_ORIGINAL_PRIVATE_ZIP_INPUT')
    require(not direct.exists(), 'PILOT_EXTRACTION_DESTINATION_EXISTS')
    require(shutil.disk_usage(Path(work)).free > 3 * 1024 ** 3, 'PILOT_EXTRACTION_DISK')
    with ZipFile(archives[0]) as zipped:
        entries = zipped.infolist()
        names = [e.filename for e in entries]
        require(len(entries) <= 250 and len(names) == len(set(n.casefold() for n in names))
                and sum(e.file_size for e in entries) < 2 * 1024 ** 3, 'ZIP_LIMITS')
        for entry in entries:
            require(not entry.is_dir() and not stat.S_ISLNK(entry.external_attr >> 16)
                    and PurePosixPath(entry.filename).as_posix() == entry.filename
                    and '..' not in PurePosixPath(entry.filename).parts, 'ZIP_MEMBER')
            within(direct, entry.filename)
        require(zipped.testzip() is None, 'ZIP_CRC')
        require(hashlib.sha256(zipped.read('run-manifest.json')).hexdigest() == PILOT_SHA, 'ZIP_MANIFEST')
        direct.mkdir(parents=True)
        for entry in entries:
            target = within(direct, entry.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(entry) as stream, target.open('xb') as output:
                shutil.copyfileobj(stream, output)
    check_run(direct, PILOT_SHA)
    return direct.resolve()


def cases_from_bundle(bundle, config):
    folder = Path(bundle) / 'data/pilot-v2'
    authenticate(folder, config)
    selection = read_json(folder / 'evaluation-selection.json')
    ids = selection['record_ids']
    require(selection['scope'] == 'DEVELOPMENT_VALIDATION_NOT_HELDOUT_TEST'
            and selection['selected_before_adapter_outputs'] is True
            and selection['count'] == len(ids) == len(set(ids)) == 20, 'LOCKED_EVALUATION_SELECTION')
    payloads = read_rows(folder / 'validation.jsonl')
    metas = read_rows(folder / 'validation.metadata.jsonl')
    lookup = {}
    for payload, meta in zip(payloads, metas):
        require(digest(payload) == meta['training_payload_sha256'], 'EVAL_PAYLOAD_HASH')
        lookup[meta['source_record_id']] = (payload, meta)
    require(set(ids) <= set(lookup), 'EVAL_NOT_VALIDATION')
    cases = []
    for rid in ids:
        payload, meta = lookup[rid]
        require(meta['split'] == 'validation' and len(payload['completion']) == 1
                and payload['completion'][0]['role'] == 'assistant', 'EVAL_PAYLOAD')
        public = loads(payload['prompt'][-1]['content'])
        cases.append(dict(record_id=rid, task_type=meta['task_type'], prompt=payload['prompt'],
            reference=payload['completion'][0]['content'], evidence=public['evidence'],
            payload_sha256=meta['training_payload_sha256']))
    return cases


def automatic_checks(text, case):
    result = dict(format_valid=False, citation_ids_valid=None, expected_behavior_match=False,
                  reference_exact_match=False, reference_token_f1=0.0,
                  semantic_correctness=None, grounded=None, citation_supports_claim=None)
    if case['task_type'] == 'hint':
        match = re.fullmatch(r'(READ|OUTLINE) \[([1-9]\d*)\]|COMPARE \[([1-9]\d*)\] \[([1-9]\d*)\]', text.strip())
        visible = {e['citation_label']: e for e in case['evidence']}
        if match:
            labels = [int(match[2])] if match[2] else [int(match[3]), int(match[4])]
            valid = all(label in visible for label in labels)
            if len(labels) == 2 and valid:
                valid = labels[0] != labels[1] and visible[labels[0]].get('source_id', labels[0]) != visible[labels[1]].get('source_id', labels[1])
            result.update(format_valid=True, citation_ids_valid=valid, expected_behavior_match=valid)
        result['reference_exact_match'] = text.strip() == case['reference'].strip()
        if text.strip() == 'INSUFFICIENT_EVIDENCE':
            result.update(format_valid=True, expected_behavior_match=result['reference_exact_match'])
        # Action-only grammar checks absence of extra answer text, not usefulness of the hint.
        result['hint_action_only'] = bool(match)
    else:
        try:
            value = loads(text.strip())
            require(isinstance(value, dict) and set(value) == {'items'}
                    and isinstance(value['items'], list) and len(value['items']) <= 24, 'OUTPUT_SCHEMA')
            for item in value['items']:
                require(isinstance(item, dict) and set(item) == {'text', 'evidence_id'}
                        and isinstance(item['text'], str) and 0 < len(item['text'].strip()) <= 1500
                        and '\n' not in item['text'] and isinstance(item['evidence_id'], str), 'OUTPUT_ITEM')
            ids = {e['evidence_id'] for e in case['evidence']}
            valid = all(item['evidence_id'] in ids for item in value['items'])
            result.update(format_valid=True, citation_ids_valid=valid if value['items'] else None,
                expected_behavior_match=valid and (bool(value['items']) != (case['task_type'] == 'insufficient_evidence')),
                reference_exact_match=value == loads(case['reference']))
        except (ValueError, TypeError, KeyError):
            pass
    def tokens(value):
        return Counter(re.findall(r'\w+', unicodedata.normalize('NFC', value).casefold()))
    predicted, target = tokens(text), tokens(case['reference'])
    overlap = sum((predicted & target).values())
    denominator = sum(predicted.values()) + sum(target.values())
    result['reference_token_f1'] = 2 * overlap / denominator if denominator else 0.0
    return result


def prompt_ids(case, tokenizer, contract):
    ids = tokenizer.apply_chat_template(case['prompt'], tokenize=True, add_generation_prompt=True)
    require(len(ids) <= contract['token_limits']['max_prompt_tokens'], 'GENERATION_PROMPT_BUDGET')
    return ids


def score_generation(text, case, status):
    require(status in ('COMPLETED', 'OUTPUT_LIMIT', 'INCOMPLETE_OR_TIMEOUT'), 'GENERATION_STATUS')
    checks = automatic_checks(text, case)
    if status != 'COMPLETED':
        checks.update(format_valid=False, citation_ids_valid=False, expected_behavior_match=False,
                      reference_exact_match=False, reference_token_f1=0.0)
    return checks


def verify_loaded_adapter(model, adapter):
    import torch
    from peft import get_peft_model_state_dict
    from safetensors.torch import load_file
    stored = load_file(Path(adapter) / 'adapter_model.safetensors', device='cpu')
    restored = get_peft_model_state_dict(model, adapter_name='pilot')
    require(set(stored) == set(restored) and all(torch.equal(stored[k], restored[k].detach().cpu()) for k in stored),
            'GPU_RELOADED_ADAPTER_TENSORS_DIFFER')


def summarize(rows):
    require(len(rows) == 40, 'FORTY_PREDICTIONS_REQUIRED')
    result = {}
    for arm in ('base', 'adapter'):
        subset = [r for r in rows if r['arm'] == arm]
        require(len(subset) == 20 and len({r['record_id'] for r in subset}) == 20, 'ARM_COVERAGE')
        citations = [r for r in subset if r['checks']['citation_ids_valid'] is not None]
        result[arm] = dict(count=20, completed=sum(r['status'] == 'COMPLETED' for r in subset),
            format_valid=sum(r['checks']['format_valid'] for r in subset),
            expected_behavior_match=sum(r['checks']['expected_behavior_match'] for r in subset),
            citation_ids_valid=sum(r['checks']['citation_ids_valid'] is True for r in citations),
            citation_eligible_count=len(citations),
            reference_exact_match=sum(r['checks']['reference_exact_match'] for r in subset),
            mean_reference_token_f1=sum(r['checks']['reference_token_f1'] for r in subset) / 20,
            mean_latency_seconds=sum(r['latency_seconds'] for r in subset) / 20,
            input_tokens=sum(r['input_tokens'] for r in subset),
            output_tokens=sum(r['output_tokens'] for r in subset))
    return dict(arms=result, scope='20_DEVELOPMENT_VALIDATION_CASES_NOT_HELDOUT_TEST',
        semantic_quality='NOT_REVIEWED', human_review_complete=False,
        limitation='Format, valid IDs, action grammar and lexical overlap do not establish factuality, grounding or citation support. Failed/truncated generations count as failures.')


def prepare(args):
    require(not args.output.exists(), 'ASSESSMENT_OUTPUT_EXISTS')
    pilot = find_pilot(args.work, args.search)
    report = audit_pilot(pilot)
    config = read_json(pilot / 'resolved-config.json')
    cases = cases_from_bundle(args.bundle, config)
    manifest = read_json(pilot / 'run-manifest.json')
    frozen = args.frozen_tools / 'scripts/qlora'
    actual = {p.name: sha_file(p) for p in frozen.glob('*.py')}
    require(actual == manifest['source_files_sha256'], 'FROZEN_TRAINER_SOURCE_MISMATCH')
    for module, expected in actual.items():
        require(sha_file(pilot / 'source/qlora' / module) == expected, 'PILOT_SOURCE_HASH')
    for path in (pilot, args.bundle, args.frozen_tools):
        require(not args.output.resolve().is_relative_to(path.resolve())
                and not path.resolve().is_relative_to(args.output.resolve()), 'OUTPUT_OVERLAPS_INPUT')
    args.output.mkdir(parents=True)
    source = args.output / 'source/assessment'
    source.mkdir(parents=True)
    for module in Path(__file__).parent.glob('*.py'):
        (source / module.name).write_bytes(module.read_bytes())
    write_json(args.output / 'context.json', dict(pilot=str(pilot), pilot_manifest_sha256=PILOT_SHA,
        bundle=str(args.bundle.resolve()), frozen_tools=str(args.frozen_tools.resolve()),
        config_sha256=digest(config), evaluation_ids=[c['record_id'] for c in cases],
        generation=GENERATION, initialization='RELOAD_FINAL_ADAPTER_NOT_NEW_TRAINING',
        scope='PRIVATE_DEVELOPMENT_CHECK', pilot_audit=report,
        source_files_sha256={p.name: sha_file(p) for p in Path(__file__).parent.glob('*.py')}))
    print('ASSESSMENT_INPUT_READY: ' + str(args.output))


def load_context(output):
    context = read_json(output / 'context.json')
    check_run(context['pilot'], PILOT_SHA)
    config = read_json(Path(context['pilot']) / 'resolved-config.json')
    require(context['pilot_manifest_sha256'] == PILOT_SHA and context['config_sha256'] == digest(config),
            'ASSESSMENT_CONTEXT_IDENTITY')
    require(context['generation'] == GENERATION, 'GENERATION_CONFIG_CHANGED')
    actual = {p.name: sha_file(p) for p in Path(__file__).parent.glob('*.py')}
    require(actual == context['source_files_sha256'], 'ASSESSMENT_CODE_CHANGED')
    for name, expected in actual.items():
        require(sha_file(output / 'source/assessment' / name) == expected, 'ASSESSMENT_SOURCE_SNAPSHOT')
    return context, config


def evaluate(args):
    context, config = load_context(args.output)
    target = args.output / 'evaluation'
    require(not target.exists(), 'EVALUATION_ALREADY_EXISTS')
    target.mkdir()
    import torch
    from transformers import GenerationConfig, set_seed
    torch.set_num_threads(2)
    data, tokenizer, contract = load_pilot(Path(context['bundle']) / 'data/pilot-v2',
                                          Path(context['bundle']) / 'tokenizer', config)
    cases = cases_from_bundle(context['bundle'], config)
    write_json(target / 'cases.json', cases)
    actual_environment = environment()
    require(actual_environment['torch'] == read_json(Path(context['pilot']) / 'environment.json')['torch'],
            'TORCH_VERSION_DIFFERS_FROM_PILOT')
    write_json(target / 'environment.json', actual_environment)
    write_json(target / 'generation-config.json', GENERATION)
    set_seed(config['seed'])
    model = load_training_model(config, cache_dir=args.cache_dir, allow_download=args.allow_model_download)
    adapter = Path(context['pilot']) / 'final-adapter'
    model.load_adapter(str(adapter), adapter_name='pilot', is_trainable=False)
    model.set_adapter('pilot')
    model.requires_grad_(False)
    model.gradient_checkpointing_disable()
    model.config.use_cache = True
    model.eval()
    verify_loaded_adapter(model, adapter)
    example = {k: torch.tensor([v], dtype=torch.long, device='cuda:0') for k, v in data['validation'][0].items()}
    with torch.inference_mode():
        reload_loss = model(**example).loss.item()
    require(math.isfinite(reload_loss), 'GPU_RELOAD_FORWARD_NONFINITE')
    write_json(target / 'reload.json', dict(status='GPU_RELOAD_PASSED',
        process_id=os.getpid(), reloaded_saved_tensors_exact=True, forward_loss=reload_loss,
        model_id=config['model_id'], revision=config['revision'], quantization='NF4_DOUBLE_QUANT_FP16',
        adapter_sha256=sha_file(adapter / 'adapter_model.safetensors'),
        base_comparison='SAME_NF4_BASE_WITH_ALL_LORA_DISABLED', requires_grad_any=any(p.requires_grad for p in model.parameters())))
    del example
    generation = GenerationConfig(**{k: v for k, v in GENERATION.items() if k != 'max_time'})

    def generate(case, arm):
        # Only prompt messages reach generate; reference answers stay outside model inputs.
        ids = prompt_ids(case, tokenizer, contract)
        inputs = torch.tensor([ids], dtype=torch.long, device='cuda:0')
        set_seed(config['seed'])
        enabled = model.disable_adapter() if arm == 'base' else nullcontext()
        with enabled, torch.inference_mode():
            torch.cuda.synchronize()
            started = time.monotonic()
            generated = model.generate(input_ids=inputs, attention_mask=torch.ones_like(inputs),
                generation_config=generation, max_time=GENERATION['max_time'])
            torch.cuda.synchronize()
            elapsed = time.monotonic() - started
        continuation = generated[0, len(ids):].detach().cpu().tolist()
        raw = tokenizer.decode(continuation, skip_special_tokens=True)
        ended = bool(continuation) and continuation[-1] == tokenizer.eos_token_id
        status = 'COMPLETED' if ended else ('OUTPUT_LIMIT' if len(continuation) >= GENERATION['max_new_tokens'] else 'INCOMPLETE_OR_TIMEOUT')
        checks = score_generation(raw, case, status)
        return dict(record_id=case['record_id'], task_type=case['task_type'], arm=arm,
            prompt_sha256=digest(case['prompt']), payload_sha256=case['payload_sha256'],
            status=status, raw_output=raw, input_tokens=len(ids), output_tokens=len(continuation),
            latency_seconds=elapsed, checks=checks)

    for arm in ('base', 'adapter'):
        generate(cases[0], arm)
    write_json(target / 'warmup.json', dict(calls=2, case_id=cases[0]['record_id'], excluded_from_timing_metrics=True))
    rows = []
    with (target / 'predictions.jsonl').open('x', encoding='utf-8') as stream:
        for index, case in enumerate(cases):
            for arm in (('base', 'adapter') if index % 2 == 0 else ('adapter', 'base')):
                row = generate(case, arm)
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                stream.flush()
                rows.append(row)
                write_json(args.output / 'phase.json', dict(phase='COMPARING', completed=len(rows), total=40,
                           record_id=case['record_id'], arm=arm))
    write_json(target / 'comparison.json', summarize(rows))
    fields = ['record_id', 'arm', 'content_correct', 'grounded', 'citation_supports_claim',
              'hint_no_answer_leak', 'decision', 'notes']
    with (target / 'review.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(record_id=row['record_id'], arm=row['arm']))
    write_json(target / 'vram.json', dict(peak_allocated_bytes=torch.cuda.max_memory_allocated(0),
                                         peak_reserved_bytes=torch.cuda.max_memory_reserved(0)))
    print('GPU_RELOAD_AND_DEVELOPMENT_COMPARISON_COMPLETED')


def audit_resume(output):
    context, config = load_context(output)
    run = output / 'resume'
    manifest = read_json(run / 'run-manifest.json')
    check_run(run, sha_file(run / 'run-manifest.json'))
    require(manifest['status'] == 'TRAINING_COMPLETED' and manifest['profile'] == 'pilot'
            and manifest['config_sha256'] == digest(config), 'RESUME_NOT_COMPLETED')
    original = Path(context['pilot'])
    require(manifest['source_files_sha256'] == read_json(original / 'run-manifest.json')['source_files_sha256'],
            'RESUME_SOURCE_CHANGED')
    args = read_json(run / 'training-arguments.json')
    require(args['max_steps'] == 50 and args['fp16'] is True and args['bf16'] is False
            and all(args[key] == value for key, value in config['training'].items()),
            'RESUME_SCHEDULE_MUST_REMAIN_50')
    env = read_json(run / 'environment.json')
    devices = read_json(run / 'training-device.json')
    require(env['cuda_available'] is True and len(env['gpus']) == 1 and 'T4' in env['gpus'][0]
            and devices['world_size'] == devices['visible_gpu_count'] == 1, 'RESUME_GPU_REQUIRED')
    loaded = read_json(run / 'model-load-report.json')
    require(loaded['model_id'] == config['model_id'] and loaded['revision'] == config['revision']
            and loaded['is_loaded_in_4bit'] is True, 'RESUME_MODEL_IDENTITY')
    ref = read_json(run / 'data-reference.json')
    require(Path(ref['resume_checkpoint']).resolve() == (original / 'checkpoint-25').resolve()
            and ref['resume_manifest_sha256'] == PILOT_SHA, 'RESUME_BINDING')
    update = read_json(run / 'adapter-update-report.json')
    require((update['start_global_step'], update['global_step'], update['applied_updates'],
             update['attempted_updates'], update['finite_gradient_checks'], update['scaler_skipped_updates'])
            == (25, 26, 1, 1, 1, 0) and update['base_frozen'] is True
            and math.isfinite(update['adapter_delta_l2']) and update['adapter_delta_l2'] > 0, 'RESUME_UPDATE_PROOF')
    events = read_rows(run / 'optimizer-events.jsonl')
    require(len(events) == 1 and events[0]['step'] == 26 and events[0]['update_applied'] is True, 'RESUME_EVENTS')
    state = read_json(run / 'checkpoint-26/trainer_state.json')
    require(state['global_step'] == 26, 'RESUME_CHECKPOINT_26')
    import torch
    # Restricted tensor/primitive loading only. Arbitrary pickle globals are never allowed in audit.
    before = torch.load(original / 'checkpoint-25/scheduler.pt', map_location='cpu', weights_only=True)
    after = torch.load(run / 'checkpoint-26/scheduler.pt', map_location='cpu', weights_only=True)
    require(before['last_epoch'] == 25 and after['last_epoch'] == 26
            and before['base_lrs'] == after['base_lrs'], 'RESUME_SCHEDULER_NOT_RESTORED')
    optimizer_before = torch.load(original / 'checkpoint-25/optimizer.pt', map_location='cpu', weights_only=True)
    optimizer_after = torch.load(run / 'checkpoint-26/optimizer.pt', map_location='cpu', weights_only=True)
    require(bool(optimizer_before['state'])
            and set(optimizer_before['state']) == set(optimizer_after['state'])
            and {int(v['step']) for v in optimizer_before['state'].values()} == {25}
            and {int(v['step']) for v in optimizer_after['state'].values()} == {26},
            'RESUME_OPTIMIZER_NOT_RESTORED')
    del optimizer_before, optimizer_after
    require(math.isfinite(read_json(run / 'eval-metrics.json')['eval_loss']), 'RESUME_EVAL_NONFINITE')
    from safetensors.torch import load_file
    final = load_file(run / 'final-adapter/adapter_model.safetensors')
    saved = load_file(run / 'checkpoint-26/adapter_model.safetensors')
    require(set(final) == set(saved) and all(torch.isfinite(v).all().item() and torch.equal(v, saved[k])
            for k, v in final.items()), 'RESUME_SAVED_ADAPTER_MISMATCH')
    return dict(status='GPU_RESUME_PASSED', start_global_step=25, global_step=26,
                applied_updates=1, scheduler_step_before=25, scheduler_step_after=26,
                optimizer_state_steps_before=[25], optimizer_state_steps_after=[26],
                original_max_steps=50, adapter_delta_l2=update['adapter_delta_l2'],
                original_pilot_untouched=True, limitation='One resume verification update, not a second pilot.')


def export(args):
    context, config = load_context(args.output)
    comparison = read_json(args.output / 'evaluation/comparison.json')
    predictions = read_rows(args.output / 'evaluation/predictions.jsonl')
    require(comparison == summarize(predictions), 'COMPARISON_RECOMPUTATION')
    cases = cases_from_bundle(context['bundle'], config)
    require(read_json(args.output / 'evaluation/cases.json') == cases
            and read_json(args.output / 'evaluation/generation-config.json') == GENERATION,
            'EVALUATION_INPUT_RECORD_CHANGED')
    require({r['record_id'] for r in predictions} == {c['record_id'] for c in cases}, 'EVAL_ID_SET')
    for row in predictions:
        case = next(c for c in cases if c['record_id'] == row['record_id'])
        require(row['prompt_sha256'] == digest(case['prompt']), 'EVAL_PROMPT_CHANGED')
        require(row['checks'] == score_generation(row['raw_output'], case, row['status']), 'CHECK_RECOMPUTATION')
        require(math.isfinite(row['latency_seconds']) and row['latency_seconds'] >= 0
                and type(row['output_tokens']) is int and 0 <= row['output_tokens'] <= 512
                and type(row['input_tokens']) is int and 0 < row['input_tokens'] <= 1536, 'GENERATION_MEASUREMENTS')
    reload = read_json(args.output / 'evaluation/reload.json')
    env = read_json(args.output / 'evaluation/environment.json')
    require(env['cuda_available'] is True and len(env['gpus']) == 1 and 'T4' in env['gpus'][0],
            'RELOAD_GPU_REQUIRED')
    require(reload['status'] == 'GPU_RELOAD_PASSED' and reload['reloaded_saved_tensors_exact'] is True
            and math.isfinite(reload['forward_loss']) and reload['requires_grad_any'] is False,
            'RELOAD_REPORT')
    require(reload['model_id'] == config['model_id'] and reload['revision'] == config['revision']
            and reload['adapter_sha256'] == sha_file(Path(context['pilot']) / 'final-adapter/adapter_model.safetensors'),
            'RELOAD_ADAPTER_IDENTITY')
    resume = audit_resume(args.output)
    report = dict(status='GPU_VERIFICATION_PASSED', pilot_manifest_sha256=PILOT_SHA,
                  reload=reload, resume=resume, comparison=comparison,
                  quality_improvement='NOT_ESTABLISHED_UNTIL_CONTENT_REVIEW')
    report_path = args.output.with_name(args.output.name + '-audit.json')
    archive = args.output.with_name(args.output.name + '.zip')
    receipt = args.output.with_name(args.output.name + '-receipt.json')
    require(not any(p.exists() for p in (report_path, archive, receipt, args.output / 'manifest.json')),
            'ASSESSMENT_EXPORT_EXISTS')
    write_json(args.output / 'summary.json', report)
    write_json(args.output / 'manifest.json', dict(status=report['status'],
        pilot_manifest_sha256=PILOT_SHA, config_sha256=digest(config),
        files=inventory(args.output)))
    write_json(report_path, report)
    needed = sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())
    require(shutil.disk_usage(args.output.parent).free > needed + 256 * 1024 ** 2, 'EXPORT_DISK')
    with ZipFile(archive, 'x', compression=ZIP_DEFLATED) as zipped:
        for path in sorted(args.output.rglob('*')):
            if path.is_file():
                zipped.write(path, path.relative_to(args.output).as_posix())
    write_json(receipt, dict(file=archive.name, sha256=sha_file(archive), size_bytes=archive.stat().st_size,
        audit_file=report_path.name, audit_sha256=sha_file(report_path),
        manifest_sha256=sha_file(args.output / 'manifest.json'), pilot_manifest_sha256=PILOT_SHA,
        scope='PRIVATE_RELOAD_RESUME_DEVELOPMENT_COMPARISON', base_weights_included=False))
    print('GPU_VERIFICATION_PASSED: ' + str(report_path))
    print('ZIP: ' + str(archive))
    print('Receipt: ' + str(receipt))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('prepare', 'evaluate', 'export'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--search', type=Path, default=Path('/kaggle/input'))
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--frozen-tools', type=Path)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--allow-model-download', action='store_true')
    args = parser.parse_args(argv)
    os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')
    os.environ.update(USE_TF='0', USE_FLAX='0', TOKENIZERS_PARALLELISM='false')
    if args.stage == 'prepare':
        require(all(p is not None for p in (args.work, args.bundle, args.frozen_tools)), 'PREPARE_ARGUMENTS')
        prepare(args)
    elif args.stage == 'evaluate':
        evaluate(args)
    else:
        export(args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
