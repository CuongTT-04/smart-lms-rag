"""Real W3 corpus -> BGE-M3 -> FAISS -> reload -> page metrics (offline, not authorization)."""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args):
    # Offline artifacts only. Never connect to Django's runtime DB or run migrations.
    from django.conf import settings
    if settings.configured:
        raise ValueError('Run in a fresh Python process with no Django settings loaded.')
    os.environ.pop('DJANGO_SETTINGS_MODULE', None)
    settings.configure(BASE_DIR=ROOT, MEDIA_ROOT=ROOT/'media', DOCUMENTS_STORAGE_ROOT=args.storage_root.resolve())
    from apps.documents.corpus_catalog import load_corpus_catalog
    from apps.ai.embeddings.base import EmbeddingConfig
    from apps.ai.retrieval.w3_contract import validate_token_budget

    catalog, chunking = load_corpus_catalog(args.corpus_manifest)
    records = [asdict(chunk) for chunk in catalog.values()]
    report = json.loads(args.corpus_manifest.read_text(encoding='utf-8'))
    config = EmbeddingConfig.from_file(args.config)
    if args.allow_download:
        config = replace(config, local_files_only=False)
    if args.device:
        config = replace(config, device=args.device)
    validate_token_budget(chunking, config, special_tokens=2)
    qa_data = json.loads(args.qa.read_text(encoding='utf-8'))
    cases = qa_data['cases']
    if not cases or len({case['qa_id'] for case in cases}) != len(cases):
        raise ValueError('QA must be nonempty with unique IDs.')
    sources = {(row['course_id'], row['document_id'], row['version_id']): row for row in report['documents']}
    for case in cases:
        if case['mode'] not in ('qa', 'hint') or not case['question'].strip():
            raise ValueError('Invalid QA question/mode.')
        for gold in case['gold_sources']:
            source = sources[(case['course_id'], gold['document_id'], gold['version_id'])]
            if type(gold['page_number']) is not int or not 1 <= gold['page_number'] <= source['page_count']:
                raise ValueError('Invalid QA physical page.')
    output = args.output_dir.resolve()
    forbidden = [ROOT/'data/corpus', args.storage_root.resolve()]
    inputs = [args.qa.resolve(), args.config.resolve(), args.corpus_manifest.resolve()]
    if any(output == p or output.is_relative_to(p) or p.is_relative_to(output) for p in forbidden+inputs):
        raise ValueError('Output must be separate from corpus, artifacts and inputs.')
    output.mkdir(parents=True, exist_ok=True)
    preflight = {'document_count': report['document_count'], 'chunk_count': len(records),
                 'qa_count': len(cases), 'chunking_config_hash': chunking.digest,
                 'embedding_config': asdict(config), 'embedding_config_hash': config.fingerprint(),
                 'corpus_manifest_sha256': digest(args.corpus_manifest), 'dataset_sha256': digest(args.qa),
                 'parser': report.get('probe_parser', 'see per-version extraction'),
                 'authorization_verified': False, 'rag_ready': False,
                 'review_status': qa_data.get('review_status', 'unknown'),
                 'validation_only': args.validate_only}
    if args.check_tokenizer:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(config.model_id, revision=config.revision,
            use_fast=True, local_files_only=config.local_files_only, trust_remote_code=False)
        validate_token_budget(chunking, config, special_tokens=tokenizer.num_special_tokens_to_add(pair=False))
        maximum = 0
        for chunk in catalog.values():
            content_count = len(tokenizer.encode(chunk.text, add_special_tokens=False, truncation=False))
            encoded_count = len(tokenizer.encode(chunk.text, add_special_tokens=True, truncation=False))
            if content_count != chunk.token_count or encoded_count > config.max_tokens:
                raise ValueError('Actual tokenizer budget mismatch: '+chunk.chunk_id)
            maximum = max(maximum, encoded_count)
        preflight.update(real_tokenizer_verified=True, maximum_encoded_tokens=maximum)
    (output/'preflight.json').write_text(json.dumps(preflight, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    if args.validate_only:
        return preflight

    from apps.ai.embeddings.service import EmbeddingService
    from apps.ai.retrieval.index import DenseIndex
    from apps.ai.retrieval.storage import save_index, load_index
    from apps.ai.retrieval.retriever import RetrievalScope, RetrievalService
    from apps.ai.evaluation.metrics import evaluate, export_report
    service = EmbeddingService(config)
    started = time.monotonic()
    model = service._load_model()
    validate_token_budget(chunking, config, special_tokens=model.tokenizer.num_special_tokens_to_add(pair=False))
    if args.reuse_index:
        index = load_index(output/'index', config)
        if index.export_chunks() != records:
            raise ValueError('Stored index differs from verified corpus. Build a fresh snapshot.')
    else:
        vectors = service.embed_chunks(records)
        index = DenseIndex(records, vectors, config)
        save_index(index, output/'index', metadata=preflight)
    loaded = load_index(output/'index', config)
    build_seconds = time.monotonic()-started
    # Explicit offline identity resolver: this evaluates source ranking, NOT runtime access rights.
    retriever = RetrievalService(loaded, service, scope_resolver=lambda scope: scope)
    predictions = {}
    reload_checks = 0
    original = RetrievalService(index, service, scope_resolver=lambda scope: scope)
    for case in cases:
        scope = RetrievalScope(str(uuid5(NAMESPACE_URL, 'w3-offline-evaluator')), case['course_id'],
            frozenset(r['version_id'] for r in records if r['course_id']==case['course_id']), mode=case['mode'])
        tick = time.monotonic()
        try:
            response = retriever.retrieve(case['question'], scope, top_k=10)
            elapsed = time.monotonic()-tick
            if reload_checks < 3:
                if response['results'] != original.retrieve(case['question'], scope, top_k=10)['results']:
                    raise ValueError('Reload changed top-k results.')
                reload_checks += 1
            predictions[case['qa_id']] = {'response': response, 'latency_seconds': elapsed}
        except Exception as exc:
            predictions[case['qa_id']] = {'error': getattr(exc, 'code', type(exc).__name__),
                'response': {'status': 'ERROR', 'results': []}, 'latency_seconds': time.monotonic()-tick}
    provenance = {**preflight, 'index_revision': retriever.index_revision,
                  'model_load_build_reload_seconds': build_seconds, 'reload_checks': reload_checks,
                  'runtime': service.runtime_info()}
    (output/'predictions.json').write_text(json.dumps({'requested_top_k': 10,
        'provenance': provenance, 'predictions': predictions}, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    rows, metrics = evaluate(cases, predictions, requested_top_k=10, provenance=provenance)
    return export_report(output, rows, metrics)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus-manifest', type=Path, required=True)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--qa', type=Path, default=ROOT/'data/qa/qa_baseline.json')
    parser.add_argument('--config', type=Path, default=ROOT/'backend/config/w3/embedding_config.json')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--allow-download', action='store_true')
    parser.add_argument('--device', choices=('cpu', 'cuda'))
    parser.add_argument('--reuse-index', action='store_true')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--check-tokenizer', action='store_true', help='Count real tokens without loading embedding weights.')
    args = parser.parse_args(argv)
    print(json.dumps(run(args), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
