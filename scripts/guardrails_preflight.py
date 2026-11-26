"""Freeze the comparison inputs without changing serving config or starting services."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
PLAN = Path('data/qa/guardrails-cases.json')
FIXTURE = Path('backend/tests/documents/w9_guardrails_fixture.py')
MODES = {'qa', 'hint', 'summary', 'history', 'followup', 'citation', 'quota', 'health'}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def shared_cases(root):
    tree = ast.parse((root / FIXTURE).read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'W9_GUARDRAIL_CASES'
            for target in node.targets
        ):
            return {case['id'] for case in ast.literal_eval(node.value)}
    raise ValueError('Missing shared case catalog')


def validate_plan(plan, root=ROOT):
    if plan['arms'] != ['base_rag', 'tuned_rag']:
        raise ValueError('Both comparison arms are required')
    cases = plan['cases']
    ids = [case['id'] for case in cases]
    if not cases or len(ids) != len(set(ids)):
        raise ValueError('Empty or duplicate case IDs')
    if {case['mode'] for case in cases} != MODES:
        raise ValueError('Missing functional or security coverage')
    shared = {case['shared_id'] for case in cases if 'shared_id' in case}
    if shared != shared_cases(root):
        raise ValueError('Shared fixture cases are not all mapped')
    for case in cases:
        if not all(case.get(key) for key in ('id', 'mode', 'actor', 'question', 'sources', 'expected', 'checks')):
            raise ValueError('Incomplete case: ' + case.get('id', '?'))
        if case['model_calls'] != 'allowed' and type(case['model_calls']) is not int:
            raise ValueError('Invalid model-call expectation')
        if set(case['checks']) - {'mock', 'live', 'ui', 'manual'}:
            raise ValueError('Unknown execution kind')
        if any(key in case for key in ('actual', 'passed', 'result')):
            raise ValueError('Expected cases must not contain acceptance results')
    required = {'retrieved_contexts_and_order', 'tokenizer', 'generation_config', 'rubric', 'fixture_snapshot'}
    if not required.issubset(plan['comparison']['same_for_both_arms']):
        raise ValueError('Comparison controls missing')
    if not plan['comparison']['do_not_modify_previous_benchmarks_or_holdout']:
        raise ValueError('Historical evaluation must remain unchanged')
    gates = plan['acceptance']
    if gates['unauthorized_disclosures'] != 0 or gates['technical_citation_validity'] != 1:
        raise ValueError('Safety gates cannot be relaxed')
    if any(gates[key] < .9 for key in ('claim_source_accuracy_target', 'claim_coverage_target')):
        raise ValueError('Semantic targets cannot be relaxed')
    return len(cases)


def candidate_identity(plan, root=ROOT):
    directory = root / plan['candidate']['directory']
    config = json.loads((directory / 'adapter_config.json').read_bytes())
    path = directory / plan['candidate']['weights']
    actual = sha256(path.read_bytes())
    if actual != plan['candidate']['sha256']:
        raise ValueError('Candidate adapter hash mismatch')
    if (config['base_model_name_or_path'], config['revision']) != (plan['model'], plan['revision']):
        raise ValueError('Candidate base model/revision mismatch')
    if config['peft_type'] != 'LORA' or config['task_type'] != 'CAUSAL_LM':
        raise ValueError('Unexpected adapter type')
    verification = json.loads((root / '.private/ayo/holdout/results/verification.json').read_bytes())
    if verification['audit']['adapter_sha256'] != actual:
        raise ValueError('Adapter differs from the holdout-evaluated artifact')
    return dict(sha256=actual, size_bytes=path.stat().st_size,
                adapter_config_sha256=sha256((directory / 'adapter_config.json').read_bytes()),
                base_model=config['base_model_name_or_path'], revision=config['revision'],
                r=config['r'], alpha=config['lora_alpha'], holdout_identity_matches=True,
                loaded_in_serving=None, serving_load_status='NOT_VERIFIED')


def source_paths(root=ROOT):
    paths = [PLAN, FIXTURE,
             Path('docs/weekly/W9/ban-giao-w9-gr-01.md'),
             Path('backend/config/ai/kaggle-dual-gpu.json'),
             Path('backend/config/ai/embedding.json'),
             Path('backend/apps/documents/retrieval_scope.py'),
             Path('backend/apps/documents/retrieval_adapter.py'),
             Path('frontend/src/components/ai/CitationViewer.jsx'),
             Path('scripts/kaggle_startup_cell.py'),
             Path('scripts/kaggle_dual_gpu_cell.py'),
             Path('scripts/append_kaggle_dual_gpu.py')]
    paths += [path.relative_to(root) for path in (root / 'backend/apps/ai').rglob('*.py')
              if '__pycache__' not in path.parts]
    return sorted(set(paths))


def capture(output, observations, root=ROOT):
    # No overwrite: changing the evaluated cases requires an explicit new snapshot.
    output = output.resolve()
    private = (root / '.private/guardrails').resolve()
    if not output.is_relative_to(private) or output == private:
        raise ValueError('Baseline must be a child of .private/guardrails')
    if output.exists():
        raise FileExistsError('Baseline already exists; use --check to verify it')
    plan = json.loads((root / PLAN).read_bytes())
    count = validate_plan(plan, root)
    adapter = candidate_identity(plan, root)
    config = json.loads((root / plan['comparison']['generation_config']).read_bytes())
    if (config['model'], config['revision']) != (plan['model'], plan['revision']):
        raise ValueError('Base profile identity mismatch')
    observed = json.loads(observations.read_bytes())
    allowed_observation_keys = {'observed_on', 'docker_running_services', 'gateway_health_http',
                                'generator', 'generation_config', 'embedding_config',
                                'index_directory', 'catalog_manifests', 'credentials_configured'}
    if set(observed) != allowed_observation_keys:
        raise ValueError('Observation schema must not contain secrets or raw responses')
    payloads = {path.as_posix(): (root / path).read_bytes() for path in source_paths(root)}
    report = dict(
        schema_version=1, status='INPUTS_FROZEN_LIVE_ACCEPTANCE_NOT_RUN',
        captured_at=datetime.now(timezone.utc).isoformat(),
        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        branch=subprocess.check_output(['git', 'branch', '--show-current'], cwd=root, text=True).strip(),
        configured_arm='base_rag', serving_identity_verified=False,
        observations=observed, base_config=config, candidate=adapter,
        case_count=count, case_results='NOT_RUN',
        paired_generation='NOT_RUN', retrieval_snapshot='PENDING_ISOLATED_RUNTIME',
        next_step='Integrate adapter in isolated inference; do not change live default yet',
        files={name: dict(sha256=sha256(data), size_bytes=len(data)) for name, data in payloads.items()},
    )
    output.mkdir(parents=True)
    with ZipFile(output / 'source.zip', 'w', ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
    report['archive_sha256'] = sha256((output / 'source.zip').read_bytes())
    (output / 'baseline.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def verify(output, root=ROOT):
    report = json.loads((output / 'baseline.json').read_bytes())
    archive_bytes = (output / 'source.zip').read_bytes()
    if sha256(archive_bytes) != report['archive_sha256']:
        raise ValueError('Frozen source archive changed')
    with ZipFile(output / 'source.zip') as archive:
        if set(archive.namelist()) != set(report['files']) or archive.testzip() is not None:
            raise ValueError('Frozen source members/CRC mismatch')
        for name, identity in report['files'].items():
            data = archive.read(name)
            if sha256(data) != identity['sha256'] or len(data) != identity['size_bytes']:
                raise ValueError('Frozen source content changed: ' + name)
    for name in (PLAN.as_posix(), FIXTURE.as_posix()):
        if sha256((root / name).read_bytes()) != report['files'][name]['sha256']:
            raise ValueError('Frozen test inputs changed: ' + name)
    plan = json.loads((root / PLAN).read_bytes())
    validate_plan(plan, root)
    if candidate_identity(plan, root)['sha256'] != report['candidate']['sha256']:
        raise ValueError('Candidate changed')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.private/guardrails/baseline')
    parser.add_argument('--observations', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        report = verify(args.output)
    elif args.observations:
        report = capture(args.output, args.observations)
    else:
        parser.error('--observations is required when capturing')
    print(json.dumps({key: report[key] for key in ('status', 'case_count', 'configured_arm',
                                                   'serving_identity_verified', 'case_results')}, indent=2))


if __name__ == '__main__':
    main()
