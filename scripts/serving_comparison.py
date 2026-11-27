"""Frozen-context serving comparison, independent of Django and training."""
import argparse
import ast
import csv
import hashlib
import json
import math
from pathlib import Path
import secrets
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def fixture_values(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    sentinels = next(ast.literal_eval(n.value) for n in tree.body
                     if isinstance(n, ast.Assign) and any(
                         isinstance(t, ast.Name) and t.id == 'SENTINELS' for t in n.targets))

    def text(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.List):
            return [text(item) for item in node.elts]
        if isinstance(node, ast.JoinedStr):
            return ''.join(text(item) for item in node.values)
        if (isinstance(node, ast.FormattedValue) and isinstance(node.value, ast.Subscript)
                and isinstance(node.value.value, ast.Name) and node.value.value.id == 'SENTINELS'):
            return sentinels[ast.literal_eval(node.value.slice)]
        raise ValueError('Unsupported fixture expression')

    values = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('allowed_pages', 'versioned_v1_pages'):
                    values[target.id] = text(node.value)
    return values


def build_cases(plan, fixture):
    values = fixture_values(fixture)

    def contexts(pages, versioned=False):
        texts = values['versioned_v1_pages' if versioned else 'allowed_pages']
        return [dict(source_id=f'S{i}', chunk_id=f'fixture-{int(versioned)}-{page}',
                     document_id=f'{int(versioned)+1:08d}-1111-4111-8111-111111111111',
                     version_id=f'{int(versioned)+3:08d}-2222-4222-8222-222222222222',
                     document_title='Shared synthetic guardrails fixture',
                     page_number=page, text=texts[page-1]) for i, page in enumerate(pages, 1)]

    requests = []
    ids = {'GR-01', 'GR-02', 'GR-03', 'GR-05', 'GR-11', 'GR-18', 'GR-20',
           'GR-21', 'GR-23', 'GR-24', 'GR-25', 'GR-26', 'GR-31'}
    for case in plan['cases']:
        if case['id'] not in ids:
            continue
        case_id = case['id']
        pages = {'GR-01':[1], 'GR-02':[2], 'GR-05':[3], 'GR-18':[1],
                 'GR-21':[2], 'GR-31':[1,2]}.get(case_id, [1,2,3])
        ctx = contexts([1,2] if case_id == 'GR-11' else pages, case_id == 'GR-11')
        if case['mode'] == 'summary':
            path = '/summary'
            body = dict(phase='map', records=[dict(id=f'B{i}', source_id=c['source_id'],
                        text=c['text']) for i, c in enumerate(ctx, 1)])
        else:
            path = '/generate'
            body = dict(question=case['question'], mode=case['mode'], contexts=ctx, exercise=None)
            if case['mode'] == 'hint':
                body['exercise'] = dict(assessment_id='public-practice', kind='TEXT',
                    title='Doc hoc lieu va trinh bay chu ky lenh.', description='', question=None)
                body['tutoring'] = dict(action='explain_task' if case_id == 'GR-26' else 'initial', step=0, history=[])
                if case_id in ('GR-24', 'GR-25'):
                    body['tutoring'] = dict(action='practice' if case_id == 'GR-25' else 'next_step', step=1,
                        history=[dict(user='Goi y doc de.', assistant='Hay xac dinh trinh tu trong nguon [1].')])
            else:
                body.update(history=[], history_protocol='chat_history_v1')
                if case_id == 'GR-18':
                    body['history'] = [dict(question='Chu ky lenh gom nhung buoc nao?',
                        answer='Fetch (nap lenh), Decode (giai ma lenh), Execute (thuc thi lenh). [1]')]
        variants = [('default', body)]
        if case_id == 'GR-25':
            variants = [(name, dict(body, question=question)) for name, question in (
                ('draft-a', 'Ban nhap cua toi: chi co Fetch. Toi con thieu y nao?'),
                ('draft-b', 'Ban nhap cua toi: Fetch, Decode, Execute. Toi con thieu y nao?'))]
        for variant, payload in variants:
            requests.append(dict(id=case_id + ':' + variant, case_id=case_id, mode=case['mode'],
                endpoint=path, payload=payload, contexts=ctx, expected=case['expected'],
                request_sha256=digest(dict(endpoint=path, payload=payload, contexts=ctx))))
    return dict(schema_version=1, plan_sha256=digest(plan), model=plan['model'], revision=plan['revision'],
        adapter_sha256=plan['candidate']['sha256'], fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
        scope='Fixed-context generation only; no retrieval, database authorization or UI acceptance',
        requests=requests, deferred_cases=[c['id'] for c in plan['cases'] if c['id'] not in ids],
        summary_scope='Map step comparison; not a completed end-to-end document summary job',
        followup_scope='QA after a fixed prior turn; suggestion display/no-extra-request is tested separately')


def technical_checks(result, contexts, summary=False):
    allowed = {c['source_id'] for c in contexts}
    if summary:
        refs = [s for p in result.get('paragraphs', []) for s in p.get('sources', [])]
    else:
        refs = [r.get('source_id') for r in result.get('output', {}).get('references', [])]
    return dict(references=len(refs), valid_references=sum(s in allowed for s in refs),
                invalid_references=sum(s not in allowed for s in refs),
                semantic_support='PENDING_REVIEW')


def request_json(url, token, data=None):
    req = Request(url, data=None if data is None else json.dumps(data).encode(),
                  headers={'Authorization':'Bearer '+token, 'Content-Type':'application/json'})
    try:
        with urlopen(req, timeout=115) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.loads(exc.read(65536))


def record_generation_attempt(path, *, case_id, arm, number, output):
    """Private comparison evidence only; never write input prompts or authentication data."""
    usage = getattr(output, 'usage', None)
    row = dict(id=case_id, arm=arm, attempt=number, text=output.text,
               finish_reason=getattr(output, 'finish_reason', None),
               usage=None if usage is None else dict(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens))
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def run(package, arm, cases_path, output):
    output.mkdir(parents=True, exist_ok=False)
    cases = json.loads(cases_path.read_bytes())
    startup = (package / 'startup.py').read_text(encoding='utf-8')
    assignments = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(startup).body
                   if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                   and n.targets[0].id in ('OHAYO_PROVIDER_BUNDLE', 'OHAYO_GATEWAY_SOURCE')}
    source_root = output / 'source'
    for name, source in assignments['OHAYO_PROVIDER_BUNDLE']['files'].items():
        assert hashlib.sha256(source.encode()).hexdigest() == assignments['OHAYO_PROVIDER_BUNDLE']['manifest']['files'][name]
        path = source_root / name
        if not path.resolve().is_relative_to(source_root.resolve()):
            raise ValueError('Unsafe source path')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')
    sys.path.insert(0, str(source_root / 'backend'))
    import torch
    from transformers import set_seed
    from apps.ai.providers.adapters import AdapterModelProvider, TrainingTokenizerProvider
    from apps.ai.providers.base import ModelConfig
    from apps.ai.rag import RAGPipeline, GenerationConfig
    set_seed(42)
    torch.set_num_threads(2)
    checkpoints = sorted(Path('/kaggle/input').rglob('checkpoint-manifest.json'))
    if not checkpoints:
        raise ValueError('Attach the saved NF4 checkpoint Input')
    if any(p.read_bytes() != checkpoints[0].read_bytes() for p in checkpoints):
        raise ValueError('Multiple different NF4 checkpoints')
    config = ModelConfig(device='cuda:0', checkpoint_path=str(checkpoints[0].parent),
        local_files_only=True, context_tokens=6144, max_input_tokens=3584,
        max_new_tokens=1024, timeout_seconds=90.0)
    manifest = json.loads((package / 'adapter/serving-manifest.json').read_bytes())
    adapter_hash = manifest['files']['adapter_model.safetensors']['sha256']
    cls = AdapterModelProvider if arm == 'tuned_rag' else TrainingTokenizerProvider
    provider = cls(config, adapter_path=package/'adapter', adapter_sha256=adapter_hash)
    if adapter_hash != cases['adapter_sha256'] or config.model_id != cases['model'] or config.revision != cases['revision']:
        raise ValueError('Model or adapter differs from the frozen cases')
    print('LOADING:', arm, flush=True)
    provider.count_tokens([dict(role='user', content='Xin chao.')])
    model = provider._runtime[0]
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    if arm == 'tuned_rag':
        identity = provider.serving_identity()
    else:
        assert not getattr(model, 'peft_config', None)
        assert not any('lora_' in name for name, _ in model.named_parameters())
        identity = dict(arm=arm, adapter_sha256=None, active_adapter=None,
                        trainable_parameters=sum(p.numel() for p in model.parameters() if p.requires_grad),
                        tokenizer_json_sha256=provider.training_tokenizer_sha256)
    gateway = {}
    exec(compile(assignments['OHAYO_GATEWAY_SOURCE'], 'frozen-gateway', 'exec'), gateway)
    public = dict(model=config.model_id, revision=config.revision, prompt_version='bounded_guidance',
                  max_input_tokens=3584, max_output_tokens=1024, timeout_seconds=90.0, temperature=0.0)
    pipeline = RAGPipeline(provider, GenerationConfig(model=config, prompt_version='bounded_guidance'))
    token = secrets.token_hex(32)
    server = gateway['start_gateway'](pipeline, token, public, port=0)
    url = f'http://127.0.0.1:{server.server_port}'
    metadata = dict(arm=arm, identity=identity, cases_sha256=hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        config=public, config_sha256=digest(public), seed=42, device='cuda:0',
        gateway_sha256=hashlib.sha256(assignments['OHAYO_GATEWAY_SOURCE'].encode()).hexdigest(),
        tokenizer_sha256=provider.training_tokenizer_sha256,
        checkpoint_manifest_sha256=hashlib.sha256(checkpoints[0].read_bytes()).hexdigest(), scope=cases['scope'])
    (output/'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    from functools import wraps
    calls = [0]
    active_case = [None, 0]
    original_generate = provider.generate

    @wraps(original_generate)
    def counted_generate(*args, **kwargs):
        calls[0] += 1
        active_case[1] += 1
        generated = original_generate(*args, **kwargs)
        record_generation_attempt(output/'generation-attempts.jsonl', case_id=active_case[0],
                                  arm=arm, number=active_case[1], output=generated)
        return generated

    provider.generate = counted_generate
    try:
        with (output/'results.jsonl').open('x', encoding='utf-8') as stream:
            for case in cases['requests']:
                active_case[:] = [case['id'], 0]
                started = time.monotonic()
                calls_before = calls[0]
                row = dict(id=case['id'], case_id=case['case_id'], arm=arm,
                           request_sha256=case['request_sha256'], http=None, result=None)
                try:
                    code, result = request_json(url+case['endpoint'], token, dict(case['payload'], config=public))
                    row.update(http=code, result=result,
                        technical=technical_checks(result, case['contexts'], case['mode']=='summary'))
                except Exception as exc:
                    row['failure_type'] = type(exc).__name__
                row['seconds'] = round(time.monotonic()-started, 4)
                row['model_calls'] = calls[0]-calls_before
                stream.write(json.dumps(row, ensure_ascii=False)+'\n')
                stream.flush()
                print(arm, row['id'], row['http'], row['seconds'], flush=True)
    finally:
        server.shutdown()
        server.server_close()
    (output/'resources.json').write_text(json.dumps(dict(
        peak_allocated_bytes=torch.cuda.max_memory_allocated(0),
        peak_reserved_bytes=torch.cuda.max_memory_reserved(0))), encoding='utf-8')


def audit(root, cases_path):
    cases = json.loads(cases_path.read_bytes())
    expected = {c['id']: c['request_sha256'] for c in cases['requests']}
    metadata, rows = {}, {}
    for arm in ('base_rag', 'tuned_rag'):
        metadata[arm] = json.loads((root/arm/'metadata.json').read_bytes())
        items = [json.loads(line) for line in (root/arm/'results.jsonl').read_text(encoding='utf-8').splitlines()]
        if len(items) != len(expected) or {r['id']:r['request_sha256'] for r in items} != expected:
            raise ValueError('Missing, duplicate or changed requests')
        if any(r['arm'] != arm for r in items) or metadata[arm]['arm'] != arm:
            raise ValueError('Wrong arm')
        if metadata[arm]['cases_sha256'] != hashlib.sha256(cases_path.read_bytes()).hexdigest():
            raise ValueError('Changed case bundle')
        rows[arm] = items
    for key in ('cases_sha256', 'config_sha256', 'config', 'gateway_sha256', 'tokenizer_sha256',
                'checkpoint_manifest_sha256', 'seed', 'device'):
        if metadata['base_rag'][key] != metadata['tuned_rag'][key]:
            raise ValueError('Unfair comparison: '+key)
    if metadata['base_rag']['identity']['adapter_sha256'] is not None:
        raise ValueError('Base contains an adapter')
    tuned = metadata['tuned_rag']['identity']
    if (tuned['adapter_sha256'] != cases['adapter_sha256']
            or not tuned['tensor_values_match'] or tuned['loaded_adapter_tensors'] != 392
            or tuned['active_adapter'] != 'default' or tuned['trainable_parameters'] != 0):
        raise ValueError('Invalid tuned identity')
    summary = dict(status='PAIRED_OUTPUTS_COLLECTED_REVIEW_PENDING', selection='KEEP_BASE_PENDING_REVIEW',
                   quality_acceptance='NOT_DECIDED', scope=cases['scope'], arms={})
    with (root/'review.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        fields = ['id', 'arm', 'http', 'seconds', 'claim_source_supported', 'claims_checked',
                  'covered_claims', 'expected_claims', 'hint_no_solution', 'injection_safe', 'decision', 'reason']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for arm, items in rows.items():
            times = sorted(r['seconds'] for r in items)
            summary['arms'][arm] = dict(total=len(items), http_200=sum(r['http']==200 for r in items),
                failures=sum(r['http']!=200 for r in items), median_seconds=(times[(len(times)-1)//2]+times[len(times)//2])/2,
                p95_seconds=times[math.ceil(.95*len(times))-1],
                invalid_references=sum(r.get('technical', {}).get('invalid_references', 0) for r in items),
                semantic_accuracy='PENDING_REVIEW', coverage='PENDING_REVIEW')
            for row in items:
                writer.writerow({k:row[k] for k in ('id', 'arm', 'http', 'seconds')})
    (root/'audit.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path)
    parser.add_argument('--arm', choices=['base_rag', 'tuned_rag'])
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    if args.audit:
        print(json.dumps(audit(args.output, args.cases), indent=2))
    else:
        run(args.package, args.arm, args.cases, args.output)
