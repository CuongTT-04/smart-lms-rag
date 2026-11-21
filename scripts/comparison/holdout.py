"""Locked instruction evaluation, independent of serving and training."""
import argparse
from collections import Counter
from contextlib import nullcontext
from importlib.metadata import version
import json
import math
from pathlib import Path
import re
import time

from scripts.comparison.protocol import digest, read_rows, write_json
from scripts.comparison.runner import LIMITS, TransformersRuntime, adapter_state, audit_assets
from scripts.qlora.data import loads, read_json, require, sha_file, tokenize_payload
from scripts.qlora.runtime import inventory, verify_inventory

ADAPTER_SHA = '51713be1e630135099f95ed08c89b5be8669b75c9e1908a1346c5c9cc4942ae7'
DATA_SHA = '95a678d4cfdaa02ff1f10b4278056e0eb72ea44f9991911fde52105e8645f3e3'
ARMS = ('rag', 'tuned_rag')  # Same evidence; adapter off versus on, not closed-book base.
TASKS = {'qa': 74, 'summary': 22, 'hint': 10, 'insufficient_evidence': 10}


def normalize(text):
    return ' '.join(text.split()).rstrip('.').casefold()


def score(raw, reference, task, messages, completed=True):
    user = json.loads(messages[-1]['content'])
    result = dict(format_valid=False, evidence_ids_valid=False, reference_exact=False,
                  reference_item_recall=0.0, refused=False)
    if not completed:
        return result
    if task == 'hint':
        match = re.fullmatch(r'(READ|COMPARE|OUTLINE) (\[[1-9][0-9]*\])(?: (\[[1-9][0-9]*\]))?', raw.strip())
        if not match:
            return result
        action, first, second = match.groups()
        if (action == 'COMPARE') != (second is not None) or first == second:
            return result
        result['format_valid'] = True
        labels = {item['citation_label'] for item in user['evidence']}
        result['evidence_ids_valid'] = all(int(label[1:-1]) in labels for label in (first, second) if label)
        result['reference_exact'] = raw.strip() == reference.strip()
        return result
    try:
        value = loads(raw)
        require(isinstance(value, dict) and set(value) == {'items'}
                and isinstance(value['items'], list), 'ITEMS_SCHEMA')
        items = value['items']
        require(all(isinstance(x, dict) and set(x) == {'text', 'evidence_id'}
                    and isinstance(x['text'], str) and bool(x['text'].strip())
                    and isinstance(x['evidence_id'], str) for x in items), 'ITEM_SCHEMA')
        result['format_valid'] = True
        result['refused'] = not items
        allowed = {x['evidence_id'] for x in user['evidence']}
        # Empty refusal has no citation: do not count it as citation success.
        result['evidence_ids_valid'] = bool(items) and all(x['evidence_id'] in allowed for x in items)
        gold = json.loads(reference)
        result['reference_exact'] = value == gold
        expected = Counter((normalize(x['text']), x['evidence_id']) for x in gold['items'])
        actual = Counter((normalize(x['text']), x['evidence_id']) for x in items)
        if expected:
            result['reference_item_recall'] = sum((expected & actual).values()) / sum(expected.values())
    except (ValueError, TypeError, KeyError):
        pass
    return result


def summarize(rows):
    result = {}
    for arm in ARMS:
        subset = [r for r in rows if r['arm'] == arm]
        require(bool(subset), 'EMPTY_ARM')
        count = len(subset)
        expected_refusals = sum(r['task_type'] == 'insufficient_evidence' for r in subset)
        predicted_refusals = sum(r['scores']['refused'] for r in subset)
        correct_refusals = sum(r['scores']['refused'] and r['task_type'] == 'insufficient_evidence' for r in subset)
        answerable = [r for r in subset if r['task_type'] != 'insufficient_evidence']
        supervised = sum(r['supervised_tokens'] for r in subset)
        loss = sum(r['nll_sum'] for r in subset) / supervised
        result[arm] = dict(rows=count, status_counts=dict(Counter(r['status'] for r in subset)),
            completion_token_weighted_loss=loss, perplexity=math.exp(loss) if loss < 700 else None,
            format_valid_rate=sum(r['scores']['format_valid'] for r in subset) / count,
            valid_citation_rate_answerable=sum(r['scores']['evidence_ids_valid'] for r in answerable) / len(answerable) if answerable else None,
            reference_exact_rate=sum(r['scores']['reference_exact'] for r in subset) / count,
            refusal_precision=correct_refusals / predicted_refusals if predicted_refusals else None,
            refusal_recall=correct_refusals / expected_refusals if expected_refusals else None,
            false_refusals=sum(r['scores']['refused'] and r['task_type'] != 'insufficient_evidence' for r in subset),
            generation_seconds=sum(r['generation_seconds'] for r in subset),
            peak_allocated_bytes=max(r['measurements']['peak_allocated_bytes'] for r in subset),
            tasks={task: dict(rows=len(group), reference_exact_rate=sum(r['scores']['reference_exact'] for r in group) / len(group),
                             mean_reference_item_recall=sum(r['scores']['reference_item_recall'] for r in group) / len(group))
                   for task in sorted({r['task_type'] for r in subset})
                   if (group := [r for r in subset if r['task_type'] == task])})
    return result


def load(package, split):
    package = Path(package)
    manifest = read_json(package / 'manifest.json')
    verify_inventory(package, manifest['files'])
    require(inventory(package, ('manifest.json',)) == manifest['files'], 'HOLDOUT_PACKAGE_FILE_SET')
    config = read_json(package / 'run-config.json')
    require(split in ('smoke', 'holdout'), 'HOLDOUT_SPLIT')
    require(config['generation'] == LIMITS
            and config['token_limits'] == dict(max_prompt_tokens=1536, max_completion_tokens=512, max_sequence_tokens=2048), 'HOLDOUT_CONFIG_LIMITS')
    require(config['adapter_sha256'] == ADAPTER_SHA and config['training_manifest_sha256'] == DATA_SHA
            and config['protocol'] == 'instruction-holdout-v1'
            and config['attempts'] == 1 and config['training'] is False, 'HOLDOUT_PIN')
    tokenizer, assets = audit_assets(package, config)
    rows = read_rows(package / 'data' / (split + '.jsonl'))
    tokens = read_rows(package / 'data' / ('tokenized-' + split + '.jsonl'))
    require(len(rows) == len(tokens) == (116 if split == 'holdout' else 4), 'HOLDOUT_COUNT')
    require(len({r['record_id'] for r in rows}) == len(rows), 'HOLDOUT_DUPLICATE_ID')
    for row, token in zip(rows, tokens):
        expected = tokenize_payload(row['payload'], tokenizer, config['token_limits'])
        require(token == dict(record_id=row['record_id'], **expected), 'HOLDOUT_TOKEN_MASK_BINDING')
        require(row['payload_sha256'] == digest(row['payload']), 'HOLDOUT_PAYLOAD_HASH')
    require(dict(Counter(r['task_type'] for r in rows)) == (TASKS if split == 'holdout' else {t: 1 for t in TASKS}), 'HOLDOUT_TASK_COUNTS')
    return config, rows, tokens, assets


def audit(package, output, split):
    config, inputs, tokens, _ = load(package, split)
    outputs = read_rows(output / 'outputs.jsonl')
    expected = {(r['record_id'], arm): (r, t) for r, t in zip(inputs, tokens) for arm in ARMS}
    require(len(outputs) == len(expected), 'HOLDOUT_OUTPUT_COUNT')
    seen = set()
    for row in outputs:
        key = row['record_id'], row['arm']
        require(key in expected and key not in seen, 'HOLDOUT_OUTPUT_ID')
        seen.add(key)
        source, token = expected[key]
        require(row['payload_sha256'] == source['payload_sha256']
                and row['prompt_sha256'] == digest(source['payload']['prompt'])
                and row['task_type'] == source['task_type'], 'HOLDOUT_OUTPUT_BINDING')
        require(row['supervised_tokens'] == token['supervised_tokens']
                and math.isfinite(row['nll_sum']) and row['nll_sum'] >= 0, 'HOLDOUT_NLL')
        enabled = row['arm'] == 'tuned_rag'
        state = row['measurements']['adapter_state']
        require(row['adapter_sha256'] == (ADAPTER_SHA if enabled else None)
                and state['enabled'] == enabled and state['layers'] == 196
                and state['disabled_layers'] == (0 if enabled else 196)
                and state['merged'] is False, 'HOLDOUT_ADAPTER_STATE')
        require(row['scores'] == score(row['raw_output'], source['payload']['completion'][0]['content'],
                                      source['task_type'], source['payload']['prompt'], row['status'] == 'completed'), 'HOLDOUT_SCORE_DRIFT')
    return dict(status='HOLDOUT_EVALUATION_AUDITED' if split == 'holdout' else 'VALIDATION_SMOKE_AUDITED',
                rows=len(outputs), adapter_sha256=config['adapter_sha256'],
                package_manifest_sha256=sha_file(package / 'manifest.json'),
                output_sha256=sha_file(output / 'outputs.jsonl'), metrics=summarize(outputs),
                failed_generations=sum(r['status'] != 'completed' for r in outputs),
                optimizer_steps=0, model_selection_on_holdout=False,
                semantic_correctness='NOT_AUTOMATICALLY_ESTABLISHED',
                limitation='Loss/format/citation-ID validity and exact-reference overlap do not prove factuality. Sources overlap the earlier main benchmark; not a new unseen-source benchmark.')


def plot(report, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figures = output / 'figures'
    figures.mkdir()
    for name, metric, ylabel in [('loss', 'completion_token_weighted_loss', 'Completion-token NLL'),
                                  ('format', 'format_valid_rate', 'Valid format rate')]:
        fig, ax = plt.subplots(figsize=(6, 4), layout='constrained')
        values = [report['metrics'][arm][metric] for arm in ARMS]
        ax.bar(['Base + evidence', 'Tuned + evidence'], values, color=['#287d8e', '#bd4b68'])
        ax.set_ylabel(ylabel)
        if name == 'format':
            ax.set_ylim(0, 1)
        fig.savefig(figures / (name + '.png'), dpi=160)
        plt.close(fig)


def run(package, output, split):
    package, output = Path(package).resolve(), Path(output).resolve()
    require(not output.exists() and not output.is_relative_to(package)
            and not package.is_relative_to(output), 'NEW_DISJOINT_HOLDOUT_RUN_REQUIRED')
    config, rows, tokens, assets = load(package, split)
    output.mkdir(parents=True)
    write_json(output / 'plan.json', dict(split=split, record_ids=[r['record_id'] for r in rows],
               package_manifest_sha256=sha_file(package / 'manifest.json'), generation=config['generation'],
               optimizer_steps=0, reference_not_in_generation_prompt=True))
    write_json(output / 'progress.json', dict(phase='LOADING_PINNED_BASE_AND_ADAPTER', rows=0, expected_rows=len(rows)*2))
    try:
        runtime = TransformersRuntime(package, config)
        torch = runtime.torch
        write_json(output / 'runtime.json', dict(assets=assets, load_seconds=runtime.load_seconds,
                   packages={p: version(p) for p in ('torch', 'transformers', 'peft', 'bitsandbytes', 'accelerate', 'safetensors')}))
        count = 0
        with (output / 'outputs.jsonl').open('x', encoding='utf-8') as stream:
            for index, (row, token) in enumerate(zip(rows, tokens)):
                prompt = row['payload']['prompt']
                ids = token['input_ids'][:token['prompt_tokens']]
                for arm in (ARMS if index % 2 == 0 else tuple(reversed(ARMS))):
                    model_input = dict(messages=prompt, arm=arm, input_tokens=len(ids), input_token_ids_sha256=digest(ids))
                    # Generation receives only prompt, never completion, metadata or task label.
                    generated, measurements = runtime.generate(model_input)
                    require(generated['status'] != 'model_error', 'HOLDOUT_GPU_MODEL_ERROR')
                    enabled = arm == 'tuned_rag'
                    runtime.model.set_adapter('selected')
                    runtime.model.requires_grad_(False)
                    with nullcontext() if enabled else runtime.model.disable_adapter():
                        adapter_state(runtime.model, enabled)
                        with torch.inference_mode():
                            loss = runtime.model(input_ids=torch.tensor([token['input_ids']], device='cuda:0'),
                                attention_mask=torch.tensor([token['attention_mask']], device='cuda:0'),
                                labels=torch.tensor([token['labels']], device='cuda:0'), use_cache=False).loss.item()
                    require(math.isfinite(loss) and loss >= 0, 'HOLDOUT_NONFINITE_LOSS')
                    record = dict(record_id=row['record_id'], task_type=row['task_type'], arm=arm,
                        payload_sha256=row['payload_sha256'], prompt_sha256=digest(prompt),
                        adapter_sha256=ADAPTER_SHA if enabled else None,
                        supervised_tokens=token['supervised_tokens'], nll_sum=loss * token['supervised_tokens'],
                        **generated, measurements=measurements,
                        scores=score(generated['raw_output'], row['payload']['completion'][0]['content'],
                                     row['task_type'], prompt, generated['status'] == 'completed'))
                    stream.write(json.dumps(record, ensure_ascii=False) + '\n')
                    stream.flush()
                    count += 1
                    write_json(output / 'progress.json', dict(phase='EVALUATING', rows=count, expected_rows=len(rows)*2))
        report = audit(package, output, split)
        write_json(output / 'audit.json', report)
        plot(report, output)
        write_json(output / 'progress.json', dict(phase='FINISHED', rows=count, expected_rows=len(rows)*2))
        write_json(output / 'artifacts.json', inventory(output))
    except Exception as exc:
        write_json(output / 'failure.json', dict(status='INCOMPLETE', error=type(exc).__name__ + ': ' + str(exc)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--split', choices=('smoke', 'holdout'), default='smoke')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if args.check_only:
        for split in ('smoke', 'holdout'):
            load(args.package, split)
        print('HOLDOUT_PACKAGE_READY_GPU_NOT_RUN')
    else:
        require(args.output is not None, 'OUTPUT_REQUIRED')
        run(args.package, args.output, args.split)
