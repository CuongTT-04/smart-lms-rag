"""One-attempt, three-arm generation; no retrieval, gold, repairs or hidden retries."""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import random
import time

from scripts.comparison.packing import build_messages, chat_tokens, schedule
from scripts.comparison.protocol import digest, read_rows, validate_cache, write_json
from scripts.qlora.data import read_json, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory

MODEL = 'Qwen/Qwen2.5-7B-Instruct'
REVISION = 'a09a35458c702b33eeacc393d103063234e8bc28'
ARMS = ('base','rag','tuned_rag')
LIMITS = dict(seed=42, do_sample=False, num_beams=1, max_new_tokens=512,
              max_input_tokens=4096, timeout_seconds=90)


def validate_config(config, mode):
    require(config['model_id'] == MODEL and config['model_revision'] == REVISION, 'RUNNER_MODEL_PIN')
    require(config['generation'] == LIMITS, 'RUNNER_GENERATION_POLICY')
    require(config['attempts'] == 1 and config['warmup_calls_per_arm'] == 2, 'RUNNER_ATTEMPTS')
    require(all(config.get(k) is False for k in ('history','response_cache','repair','retries')), 'RUNNER_FEATURE_POLICY')
    require(mode in ('smoke','dev','main'), 'RUNNER_MODE')
    if mode == 'main':
        require(config['stage'] == 'MAIN_FROZEN' and config['main_authorized'] is True
                and isinstance(config.get('freeze_sha256'), str) and len(config['freeze_sha256']) == 64, 'MAIN_NOT_FROZEN')
    else:
        require(config['stage'] in ('DEV_ONLY','MAIN_FROZEN'), 'RUNNER_STAGE')


def validate_inputs(inputs, caches, models, tokenizer):
    from jsonschema import Draft202012Validator, FormatChecker
    validator = Draft202012Validator(read_json(Path(__file__).resolve().parents[2] / 'data/comparison/input.schema.json'), format_checker=FormatChecker())
    expected = {r['qa_id']:r for r in inputs}
    require(len(expected) == len(inputs) and bool(inputs), 'INPUT_IDS')
    for row in inputs:
        require(set(row) == {'qa_id','question','scope_id'}, 'INPUT_GOLD_OR_UNKNOWN_FIELD')
        validator.validate(row)
    lookup = {r['qa_id']:r for r in caches}
    require(len(lookup) == len(caches) and set(lookup) == set(expected), 'CACHE_ID_SET')
    for rid, row in lookup.items():
        validate_cache(row)
        require(all(row[k] == expected[rid][k] for k in expected[rid]), 'STALE_CACHE_QUESTION_OR_SCOPE')
    model_map = {}
    fields = {'qa_id','arm','messages','input_sha256','contexts_sha256','input_token_ids_sha256','input_tokens'}
    for row in models:
        require(set(row) == fields and row['qa_id'] in expected and row['arm'] in ARMS, 'MODEL_INPUT_FIELDS')
        key = row['qa_id'],row['arm']
        require(key not in model_map, 'DUPLICATE_MODEL_INPUT')
        messages = build_messages(lookup[key[0]],key[1])
        require(row['messages'] == messages and row['input_sha256'] == digest(messages), 'MODEL_PROMPT_BINDING')
        require(row['contexts_sha256'] == (None if key[1] == 'base' else lookup[key[0]]['contexts_sha256']), 'MODEL_CONTEXT_BINDING')
        tokens = chat_tokens(tokenizer,messages)
        require(row['input_tokens'] == len(tokens) and row['input_token_ids_sha256'] == digest(tokens)
                and 0 < len(tokens) <= 4096, 'MODEL_TOKEN_BINDING')
        model_map[key] = row
    require(set(model_map) == {(q,a) for q in expected for a in ARMS}, 'THREE_ARM_COVERAGE')
    for rid in expected:
        left, right = model_map[rid,'rag'], model_map[rid,'tuned_rag']
        require(all(left[k] == right[k] for k in fields - {'arm'}), 'RAG_TUNED_INPUT_DIFFERENCE')
    return model_map


def audit_assets(package, config):
    from safetensors import safe_open
    from transformers import AutoTokenizer
    package = Path(package)
    reference = read_json(package / 'tokenizer-reference.json')
    require(reference['model_id'] == MODEL and reference['revision'] == REVISION, 'TOKENIZER_MODEL_PIN')
    for name, expected in reference['files'].items():
        path = package / 'tokenizer' / name
        require(path.stat().st_size == expected['size_bytes'] and sha_file(path) == expected['sha256'], 'TOKENIZER_ASSET_HASH')
    tokenizer = AutoTokenizer.from_pretrained(package / 'tokenizer', local_files_only=True, trust_remote_code=False)
    require(hashlib.sha256(tokenizer.chat_template.encode()).hexdigest() == reference['chat_template_sha256']
            and tokenizer.eos_token_id == reference['eos_token_id'] and tokenizer.pad_token_id == reference['pad_token_id'], 'TOKENIZER_TEMPLATE_OR_IDS')
    adapter = package / 'adapter'
    require(sha_file(adapter / 'adapter_model.safetensors') == config['adapter_sha256']
            and sha_file(adapter / 'adapter_config.json') == config['adapter_config_sha256'], 'ADAPTER_BYTES')
    settings = read_json(adapter / 'adapter_config.json')
    require(settings['base_model_name_or_path'] == MODEL and settings['revision'] == REVISION
            and settings['peft_type'] == 'LORA' and settings['task_type'] == 'CAUSAL_LM'
            and settings['r'] == 8 and settings['lora_alpha'] == 16 and settings['bias'] == 'none'
            and settings['modules_to_save'] is None and not settings['use_dora'], 'ADAPTER_CONFIG')
    shapes = {}
    with safe_open(adapter / 'adapter_model.safetensors', framework='pt', device='cpu') as saved:
        for key in saved.keys():
            require('.lora_A.' in key or '.lora_B.' in key, 'UNEXPECTED_ADAPTER_TENSOR')
            shape = saved.get_slice(key).get_shape()
            require(len(shape) == 2 and shape[0 if '.lora_A.' in key else 1] == 8, 'ADAPTER_RANK')
            shapes[key] = shape
    require(len(shapes) == 392, 'ADAPTER_LAYER_COVERAGE')
    expected_shapes = {}
    dimensions = dict(q_proj=(3584,3584), k_proj=(3584,512), v_proj=(3584,512), o_proj=(3584,3584),
                      gate_proj=(3584,18944), up_proj=(3584,18944), down_proj=(18944,3584))
    for layer in range(28):
        for target, (in_features,out_features) in dimensions.items():
            branch = 'self_attn' if target in ('q_proj','k_proj','v_proj','o_proj') else 'mlp'
            prefix = f'base_model.model.model.layers.{layer}.{branch}.{target}'
            expected_shapes[prefix+'.lora_A.weight'] = [8,in_features]
            expected_shapes[prefix+'.lora_B.weight'] = [out_features,8]
    require(shapes == expected_shapes, 'ADAPTER_QWEN_LAYER_DIMENSIONS')
    for key, shape in shapes.items():
        if '.lora_A.' in key:
            other = key.replace('.lora_A.','.lora_B.')
            require(other in shapes and shapes[other][1] == shape[0], 'ADAPTER_PAIR')
    return tokenizer, dict(status='TOKENIZER_AND_ADAPTER_BYTES_CONFIG_SHAPES_PASSED', adapter_tensors=len(shapes),
        adapter_parameters=sum(a*b for a,b in shapes.values()), adapter_sha256=config['adapter_sha256'],
        base_weights_loaded=False, runtime_reload='PENDING_GPU_SMOKE', model_id=MODEL, revision=REVISION)


def adapter_state(model, enabled):
    from peft.tuners.tuners_utils import BaseTunerLayer
    layers = [m for m in model.modules() if isinstance(m,BaseTunerLayer)]
    require(bool(layers), 'NO_LORA_LAYERS')
    require(all(bool(m.disable_adapters) == (not enabled) and not m.merged_adapters for m in layers), 'ADAPTER_DISABLE_OR_MERGE_STATE')
    require(all(list(m.active_adapters) == ['selected'] for m in layers), 'ADAPTER_ACTIVE_NAME')
    return dict(enabled=enabled, layers=len(layers), disabled_layers=sum(bool(m.disable_adapters) for m in layers), merged=False, active_adapter='selected')


class TransformersRuntime:
    def __init__(self, package, config):
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, BitsAndBytesConfig
        require(torch.cuda.is_available() and torch.cuda.device_count() == 1, 'ONE_VISIBLE_CUDA_GPU_REQUIRED')
        require('T4' in torch.cuda.get_device_name(0), 'PRIMARY_T4_REQUIRED')
        for name, expected in read_json(package / 'tokenizer-reference.json')['packages'].items():
            require(version(name) == expected, 'INFERENCE_LIBRARY_PIN:' + name)
        require(version('peft') == '0.17.1', 'PEFT_VERSION_PIN')
        self.torch, self.config = torch, config
        self.tokenizer, self.assets = audit_assets(package,config)
        random.seed(42)
        torch.manual_seed(42)
        torch.cuda.manual_seed_all(42)
        quantization = BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16)
        started = time.perf_counter()
        base = AutoModelForCausalLM.from_pretrained(MODEL, revision=REVISION, trust_remote_code=False,
            torch_dtype=torch.float16, quantization_config=quantization, device_map={'':0}, attn_implementation='sdpa')
        require(base.config.model_type == 'qwen2' and base.config.num_hidden_layers == 28
                and base.config.hidden_size == 3584 and getattr(base.config,'_commit_hash',None) == REVISION, 'LOADED_BASE_IDENTITY')
        self.model = PeftModel.from_pretrained(base, package / 'adapter', adapter_name='selected', is_trainable=False)
        self.model.eval()
        require(not any(p.requires_grad for p in self.model.parameters()), 'INFERENCE_MODEL_TRAINABLE')
        require(getattr(base,'is_loaded_in_4bit',False), 'NF4_NOT_LOADED')
        self.load_seconds = time.perf_counter()-started

    def generate(self, row):
        from transformers import StoppingCriteria, StoppingCriteriaList
        torch = self.torch
        start_tokens = time.perf_counter()
        ids = chat_tokens(self.tokenizer,row['messages'])
        require(digest(ids) == row['input_token_ids_sha256'] and len(ids) == row['input_tokens'], 'RUNTIME_TOKEN_DRIFT')
        inputs = torch.tensor([ids],device='cuda:0')
        tokenization_seconds = time.perf_counter()-start_tokens
        enabled = row['arm'] == 'tuned_rag'
        self.model.set_adapter('selected')
        self.model.requires_grad_(False)
        context = nullcontext() if enabled else self.model.disable_adapter()
        with context:
            state = adapter_state(self.model,enabled)
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            class Budget(StoppingCriteria):
                last = None
                first_token_seconds = None
                timed_out = False
                def __call__(self, input_ids, scores, **kwargs):
                    self.last = input_ids.detach()
                    if self.first_token_seconds is None:
                        torch.cuda.synchronize()
                        self.first_token_seconds = time.perf_counter()-started
                    self.timed_out = time.perf_counter()-started >= 90
                    return self.timed_out
            budget = Budget()
            error = None
            try:
                with torch.inference_mode():
                    generated = self.model.generate(input_ids=inputs, attention_mask=torch.ones_like(inputs),
                        do_sample=False,num_beams=1,max_new_tokens=512,use_cache=True,
                        return_dict_in_generate=False,output_scores=False,
                        eos_token_id=self.tokenizer.eos_token_id,pad_token_id=self.tokenizer.pad_token_id,
                        stopping_criteria=StoppingCriteriaList([budget]))
                suffix = generated[0,len(ids):].detach().cpu().tolist()
            except Exception as exc:
                error = type(exc).__name__ + ': ' + str(exc)
                suffix = budget.last[0,len(ids):].cpu().tolist() if budget.last is not None else []
            torch.cuda.synchronize()
            seconds = time.perf_counter()-started
            timeout = budget.timed_out or seconds >= 90
            status = 'model_error' if error else 'timeout' if timeout else 'completed' if suffix and suffix[-1] == self.tokenizer.eos_token_id else 'output_limit'
            result = dict(raw_output=self.tokenizer.decode(suffix,skip_special_tokens=True), status=status,
                stop_reason='exception' if error else 'timeout' if timeout else 'eos' if status == 'completed' else 'max_new_tokens',
                output_tokens=len(suffix), generation_seconds=seconds, error=error)
            timing = dict(adapter_state=state, tokenization_seconds=tokenization_seconds,
                first_token_seconds=budget.first_token_seconds, peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                peak_reserved_bytes=torch.cuda.max_memory_reserved(), timeout_enforcement='COOPERATIVE_AT_TOKEN_BOUNDARIES_NOT_HARD_GPU_PREEMPTION')
        return result,timing


def audit_outputs(expected, outputs, adapter_sha256):
    from jsonschema import Draft202012Validator
    schema = read_json(Path(__file__).resolve().parents[2] / 'data/comparison/output.schema.json')
    validator = Draft202012Validator(schema)
    mapping = {(r['qa_id'],r['arm']):r for r in expected}
    require(len(mapping) == len(expected) and bool(mapping), 'OUTPUT_EXPECTED_IDS')
    seen, run_ids, statuses = set(), set(), {}
    for row in outputs:
        validator.validate(row)
        key = row['qa_id'],row['arm']
        require(key in mapping and key not in seen, 'OUTPUT_DUPLICATE_OR_UNKNOWN')
        seen.add(key)
        run_ids.add(row['run_id'])
        source = mapping[key]
        require(all(row[k] == source[k] for k in ('input_sha256','contexts_sha256','input_token_ids_sha256','input_tokens')), 'OUTPUT_INPUT_BINDING')
        enabled = key[1] == 'tuned_rag'
        require(row['adapter_enabled'] == enabled and row['adapter_sha256'] == (adapter_sha256 if enabled else None), 'OUTPUT_ADAPTER_BINDING')
        require(math.isfinite(row['generation_seconds']) and row['output_tokens'] <= 512, 'OUTPUT_MEASUREMENT')
        statuses[row['status']] = statuses.get(row['status'],0)+1
    require(seen == set(mapping) and len(run_ids) == 1, 'OUTPUT_INCOMPLETE_OR_MIXED_RUNS')
    return dict(status='OUTPUT_IDENTITY_AND_COMPLETENESS_PASSED', rows=len(seen), status_counts=statuses,
                factuality='NOT_EVALUATED', failure_rows=len(seen)-statuses.get('completed',0),
                limitation='Output identity checks do not prove semantic quality or independently reload the adapter.')


def run(package, output, mode='dev', runtime_factory=TransformersRuntime):
    package, output = Path(package).resolve(), Path(output).resolve()
    require(not output.exists() and not output.is_relative_to(package) and not package.is_relative_to(output), 'NEW_DISJOINT_RUN_OUTPUT_REQUIRED')
    manifest = read_json(package / 'manifest.json')
    verify_inventory(package,manifest['files'])
    require(set(inventory(package,('manifest.json',))) == set(manifest['files']), 'RUN_PACKAGE_FILE_SET')
    config = read_json(package / 'run-config.json')
    validate_config(config,mode)
    split = 'main' if mode == 'main' else 'dev'
    if mode == 'main':
        require(sha_file(package / 'freeze.json') == config['freeze_sha256'], 'MAIN_FREEZE_FILE_HASH')
        freeze = read_json(package / 'freeze.json')
        require(freeze['status'] == 'FROZEN_FOR_MAIN' and freeze['adapter_sha256'] == config['adapter_sha256']
                and freeze['generation_sha256'] == digest(config['generation']), 'MAIN_FREEZE_BINDING')
        expected_files = {n:sha_file(package / 'inputs' / ('main.'+n)) for n in
                          ('inputs.jsonl','cache.jsonl','model-inputs.jsonl','schedule.json')}
        require(freeze['input_files'] == expected_files, 'MAIN_FREEZE_INPUT_FILES')
    inputs, caches, models = [read_rows(package / 'inputs' / (split+'.'+name+'.jsonl')) for name in ('inputs','cache','model-inputs')]
    require(len(inputs) == (300 if split == 'main' else 30), 'RUN_EXPECTED_CASE_COUNT')
    require(all(r['qa_id'].startswith('Q' if split == 'main' else 'D') for r in inputs), 'SPLIT_ID_NAMESPACE')
    tokenizer, assets = audit_assets(package,config)
    model_map = validate_inputs(inputs,caches,models,tokenizer)
    planned = read_json(package / 'inputs' / (split+'.schedule.json'))
    require(planned == schedule(inputs), 'ARM_SCHEDULE_CHANGED')
    if mode == 'smoke':
        planned = planned[:1]
    output.mkdir(parents=True)
    run_id = mode+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    write_json(output / 'run-plan.json',dict(run_id=run_id,mode=mode,package_manifest_sha256=sha_file(package / 'manifest.json'),
        config_sha256=sha_file(package / 'run-config.json'),expected_rows=3*len(planned),schedule=planned,assets=assets))
    count = 0
    try:
        write_json(output / 'progress.json',dict(phase='LOADING_PINNED_BASE',rows=0,expected_rows=3*len(planned)))
        runtime = runtime_factory(package,config)
        warmup_calls=0
        write_json(output / 'progress.json',dict(phase='WARMUP',rows=0,warmup_calls=0,expected_rows=3*len(planned)))
        with (output / 'warmup.jsonl').open('x',encoding='utf-8') as warm:
            for arm in ARMS:
                for _ in range(2):
                    result,timing = runtime.generate(model_map[inputs[0]['qa_id'],arm])
                    warm.write(json.dumps(dict(arm=arm,**result,**timing),ensure_ascii=False)+'\n')
                    warm.flush()
                    warmup_calls += 1
                    write_json(output / 'progress.json',dict(phase='WARMUP',rows=0,warmup_calls=warmup_calls,expected_rows=3*len(planned)))
                    require(result['status'] == 'completed', 'WARMUP_FAILED_DO_NOT_START_ASSIGNED_CASES')
        with (output / 'outputs.jsonl').open('x',encoding='utf-8') as stream, (output / 'measurements.jsonl').open('x',encoding='utf-8') as measure:
            for case in planned:
                for arm in case['arms']:
                    row = model_map[case['qa_id'],arm]
                    result,timing = runtime.generate(row)
                    record = dict(run_id=run_id,qa_id=row['qa_id'],arm=arm,
                        **{k:row[k] for k in ('input_sha256','contexts_sha256','input_token_ids_sha256','input_tokens')},
                        adapter_enabled=arm == 'tuned_rag', adapter_sha256=config['adapter_sha256'] if arm == 'tuned_rag' else None, **result)
                    stream.write(json.dumps(record,ensure_ascii=False)+'\n')
                    stream.flush()
                    measure.write(json.dumps(dict(qa_id=row['qa_id'],arm=arm,**timing),ensure_ascii=False)+'\n')
                    measure.flush()
                    count += 1
                    write_json(output / 'progress.json',dict(phase='GENERATION',rows=count,expected_rows=3*len(planned)))
                    print(f'{count}/{len(planned)*3} {row["qa_id"]} {arm}: {record["status"]}',flush=True)
        write_json(output / 'runtime.json',dict(status='GENERATION_FINISHED_PENDING_READBACK',rows=count,
            run_id=run_id,base_model_id=MODEL,base_revision=REVISION,load_seconds=runtime.load_seconds,
            packages={p:version(p) for p in ('torch','transformers','peft','bitsandbytes','accelerate','safetensors')},
            factuality='NOT_EVALUATED', retry_count=0, cache='FROZEN_RETRIEVAL_NOT_LIVE_E2E'))
        selected = [model_map[c['qa_id'],a] for c in planned for a in c['arms']]
        audited=audit_outputs(selected,read_rows(output / 'outputs.jsonl'),config['adapter_sha256'])
        write_json(output / 'audit.json',audited)
        write_json(output / 'progress.json',dict(phase='FINISHED_IDENTITY_CHECKED',rows=count,expected_rows=3*len(planned),failure_rows=audited['failure_rows']))
    except Exception as exc:
        write_json(output / 'failure.json',dict(run_id=run_id,status='INCOMPLETE_DO_NOT_CLAIM_SUCCESS',persisted_rows=count,
            error=type(exc).__name__+': '+str(exc),resume='New run revision required; never silently retry or overwrite.'))
        write_json(output / 'progress.json',dict(phase='INCOMPLETE',rows=count,expected_rows=3*len(planned)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=('smoke','dev','main'),default='smoke')
    parser.add_argument('--check-only',action='store_true')
    args = parser.parse_args()
    if args.check_only:
        manifest = read_json(args.package / 'manifest.json')
        verify_inventory(args.package,manifest['files'])
        require(set(inventory(args.package,('manifest.json',))) == set(manifest['files']), 'RUN_PACKAGE_FILE_SET')
        config = read_json(args.package / 'run-config.json')
        validate_config(config,args.mode)
        tokenizer, report = audit_assets(args.package,config)
        for split in ('dev',):
            validate_inputs(*[read_rows(args.package / 'inputs' / (split+'.'+n+'.jsonl')) for n in ('inputs','cache','model-inputs')],tokenizer)
        print(json.dumps(report,indent=2))
    else:
        run(args.package,args.output,args.mode)
