"""Lock adapter selection and experiment inputs without running generation."""
import argparse
from pathlib import Path

from scripts.comparison.protocol import digest, read_rows, write_json
from scripts.comparison.runner import LIMITS, audit_assets, validate_config, validate_inputs
from scripts.comparison.packing import schedule
from scripts.qlora.data import read_json, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory

ROOT = Path(__file__).resolve().parents[2]
SELECTED = '51713be1e630135099f95ed08c89b5be8669b75c9e1908a1346c5c9cc4942ae7'


def verify_locked(root, files):
    for name, info in files.items():
        path = (root / name).resolve()
        require(path.is_relative_to(root.resolve()), 'FREEZE_PATH_ESCAPE')
        require(path.stat().st_size == info['size_bytes'] and sha_file(path) == info['sha256'],
                'FREEZE_SOURCE_CHANGED')


def decide(recommendation, config):
    require(recommendation['recommended_adapter_sha256'] == config['adapter_sha256'] == SELECTED,
            'FREEZE_SELECTED_ADAPTER')
    require(recommendation['new_correctness_total'] > recommendation['old_correctness_total'],
            'FREEZE_SELECTION_EVIDENCE')
    validate_config(config, 'dev')
    return dict(adapter_sha256=SELECTED, decision='SELECT_NEW_FINAL_ADAPTER',
                reason='Higher aggregate dev correctness, citation support and renderer success.',
                limitations=['THMLN correctness 20/20 to 16/20; four paired losses.',
                             'Faithfulness 61/62 to 71/73; not universal superiority.',
                             'Reused 30 answerable dev cases; no insufficient-evidence refusal estimate.',
                             'Single source-grounded rubric review, not independent peer/API judging.'],
                chatbot_adapter_changed=False)


def build(output):
    output = output.resolve()
    require(output.resolve().is_relative_to(ROOT / '.private') and not output.exists(),
            'NEW_PRIVATE_FREEZE_REQUIRED')
    state_path = ROOT / '.private/comparison/experiment-readiness.json'
    state = read_json(state_path)
    prepared = ROOT / '.private/comparison/prepared'
    assessment = ROOT / state['dev_assessment_path']
    source_package = ROOT / '.private/comparison/runs/full-20261112T192034516377Z-dev-package-linux'
    config = read_json(source_package / 'run-config.json')
    verify_inventory(source_package, read_json(source_package / 'manifest.json')['files'])
    selection = decide(read_json(assessment / 'recommendation.json'), config)
    tokenizer, assets = audit_assets(source_package, config)
    retrieval = ROOT / state['retrieval_path']
    require(sha_file(retrieval / 'complete.json') == state['retrieval_complete_sha256'], 'FREEZE_RETRIEVAL')
    verify_inventory(retrieval, read_json(retrieval / 'complete.json')['files'])
    training = ROOT / state['training_path']
    benchmark = ROOT / state['benchmark_path']
    for folder, pin in ((training, 'normalized_training_manifest_sha256'),
                        (benchmark, 'benchmark_manifest_sha256')):
        require(sha_file(folder / 'manifest.json') == state[pin], 'FREEZE_DATASET_PIN')
        verify_inventory(folder, read_json(folder / 'manifest.json')['files'])
    require(config['generation'] == LIMITS, 'FREEZE_GENERATION')
    inputs = {}
    for split, count in (('dev', 30), ('main', 300)):
        rows = [read_rows(retrieval / (split + '.' + n + '.jsonl'))
                for n in ('inputs', 'cache', 'model-inputs')]
        require(len(rows[0]) == count and len(rows[2]) == count * 3, 'FREEZE_COUNTS')
        validate_inputs(*rows, tokenizer)
        require(read_json(retrieval / (split + '.schedule.json')) == schedule(rows[0]), 'FREEZE_SCHEDULE')
        inputs[split] = {n: sha_file(retrieval / (split + '.' + n)) for n in
                         ('inputs.jsonl', 'cache.jsonl', 'model-inputs.jsonl', 'schedule.json')}
    require(inputs['dev'] == {n: sha_file(source_package / 'inputs' / ('dev.' + n))
                             for n in inputs['dev']}, 'FREEZE_DEV_COMPARABILITY')
    full = ROOT / state['expanded_full_run_path']
    require(sha_file(full / 'run-manifest.json') == state['expanded_full_run_manifest_sha256'],
            'FREEZE_TRAINING_RUN')
    require(sha_file(full / 'final-adapter/adapter_model.safetensors') == SELECTED, 'FREEZE_FINAL_BYTES')
    paths = [retrieval / (s + '.' + n) for s in inputs for n in inputs[s]]
    paths += [source_package / n for n in inventory(source_package) if not n.startswith('inputs/')]
    paths += [training / 'manifest.json', benchmark / 'manifest.json', benchmark / 'main.references.jsonl',
              benchmark / 'reviews.csv', prepared / 'semantic-review.json', full / 'run-manifest.json']
    paths += [assessment / n for n in inventory(assessment)]
    files = {p.relative_to(ROOT).as_posix(): dict(sha256=sha_file(p), size_bytes=p.stat().st_size)
             for p in paths}
    verify_locked(ROOT, files)
    freeze = dict(schema_version='comparison-freeze-v1', status='FROZEN_FOR_MAIN',
                  adapter_sha256=SELECTED, generation_sha256=digest(config['generation']),
                  input_files=inputs['main'], dev_input_files=inputs['dev'], selection=selection,
                  benchmark_interpretation='SAME_DOMAIN_WITH_DISCLOSED_PARTIAL_CONCEPT_OVERLAP',
                  benchmark_cases=300, answerable=240, insufficient_evidence=60, arms=['base','rag','tuned_rag'],
                  retrieval='FROZEN_COURSE_FILTERED_TOP5_NOT_LIVE_END_TO_END',
                  training_manifest_sha256=state['normalized_training_manifest_sha256'],
                  benchmark_manifest_sha256=state['benchmark_manifest_sha256'],
                  retrieval_complete_sha256=state['retrieval_complete_sha256'],
                  fresh_package_smoke_required=True, main_execution_started=False,
                  evaluation_policy=dict(raw_outputs_immutable=True, failures_kept_in_denominator=True,
                      gold_excluded_from_generator=True, no_main_feedback_for_selection=True,
                      semantic_review='SOURCE_GROUNDED_RUBRIC_WITH_REVIEWER_PROVENANCE',
                      external_version_pinned_judge_completed=False),
                  rights='DECLARED_NOT_VERIFIED_PRIVATE_RESEARCH_ONLY', public_redistribution_allowed=False)
    output.mkdir(parents=True)
    write_json(output / 'freeze.json', freeze)
    config.update(stage='MAIN_FROZEN', main_authorized=True, freeze_sha256=sha_file(output / 'freeze.json'))
    validate_config(config, 'main')
    write_json(output / 'run-config.json', config)
    write_json(output / 'source-lock.json', dict(files=files))
    write_json(output / 'preflight.json', dict(status='STEP6_FROZEN_MAIN_NOT_RUN', assets=assets,
        validated_cases=330, validated_model_inputs=990, fresh_package_smoke='REQUIRED_BEFORE_MAIN',
        qwen_weights_loaded=False, optimizer_steps=0))
    write_json(output / 'manifest.json', dict(files=inventory(output)))
    verify_inventory(output, read_json(output / 'manifest.json')['files'])
    activate(output)
    return freeze


def activate(output):
    output = output.resolve()
    require(output.is_relative_to(ROOT / '.private'), 'PRIVATE_FREEZE_REQUIRED')
    verify_inventory(output, read_json(output / 'manifest.json')['files'])
    verify_locked(ROOT, read_json(output / 'source-lock.json')['files'])
    freeze = read_json(output / 'freeze.json')
    config = read_json(output / 'run-config.json')
    require(sha_file(output / 'freeze.json') == config['freeze_sha256'], 'FREEZE_CONFIG_BINDING')
    require(freeze['adapter_sha256'] == config['adapter_sha256'] == SELECTED, 'FREEZE_SELECTED_ADAPTER')
    validate_config(config, 'main')
    state_path = ROOT / '.private/comparison/experiment-readiness.json'
    state = read_json(state_path)
    state.update(status='STEP6_FROZEN_MAIN_PACKAGE_AND_SMOKE_NEXT', expanded_adapter_selected=True,
        selected_adapter_sha256=SELECTED, benchmark_interpretation_requires_freeze_decision=False,
        benchmark_interpretation=freeze['benchmark_interpretation'],
        freeze_path=output.relative_to(ROOT).as_posix(), freeze_sha256=config['freeze_sha256'],
        frozen_config_sha256=sha_file(output / 'run-config.json'),
        main_authorized=False, main_execution_gate='PACKAGE_BOUND_FRESH_SMOKE_REQUIRED',
        main_completed=False)
    state.pop('expanded_candidate_smoke_artifact', None)
    write_json(state_path, state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
