"""Rebuild an isolated source-only index, real caches and semantic-screen evidence."""
import argparse
from dataclasses import asdict
from importlib.metadata import version
import os
from pathlib import Path
import sys
import time

from scripts.comparison.packing import build_messages, chat_tokens, pack_contexts, schedule
from scripts.comparison.protocol import digest, read_rows, validate_cache, write_json, write_rows
from scripts.qlora.data import read_json, require, sha_file, within
from scripts.qlora.runtime import inventory, verify_inventory

ROOT = Path(__file__).resolve().parents[2]
REVISION = '5617a9f61b028005a4858fdac845db406aefb181'


def embed_block(service, rows, path, descriptor):
    import numpy as np
    binding = digest(dict(rows=rows, descriptor=descriptor))
    if path.exists():
        with np.load(path, allow_pickle=False) as saved:
            require(str(saved['binding']) == binding, 'EMBEDDING_RESUME_BINDING')
            vectors, counts = saved['vectors'], saved['counts']
    else:
        result = service.embed_chunks(rows)
        vectors, counts = result.vectors, np.array(result.token_counts)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, vectors=vectors, counts=counts, binding=binding)
    require(vectors.shape == (len(rows), 1024) and vectors.dtype == np.float32
            and np.isfinite(vectors).all() and np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4), 'EMBEDDING_ARRAY')
    return vectors, counts


def prepare(corpus, benchmark, dev, handoff, output, index_source=None):
    import numpy as np
    import torch
    from pypdf import PdfReader
    from transformers import AutoTokenizer
    backend = str(ROOT / 'backend')
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from apps.documents.processors.chunker import chunk_extraction
    from apps.documents.retrieval_contracts import ChunkingConfig
    from apps.ai.embeddings.base import EmbeddedChunks, EmbeddingConfig
    from apps.ai.embeddings.service import EmbeddingService
    from apps.ai.retrieval.index import DenseIndex
    from apps.ai.retrieval.storage import load_index, save_index
    corpus, benchmark, dev, handoff, output = map(Path, (corpus, benchmark, dev, handoff, output))
    require(output.resolve().is_relative_to(ROOT / '.private') and not (output / 'complete.json').exists(), 'NEW_PRIVATE_PREPARATION_REQUIRED')
    torch.set_num_threads(min(8, os.cpu_count() or 2))
    registry = read_json(corpus / 'source-manifest.json')
    source_inputs = dict(main=benchmark / 'main.inputs.jsonl', dev=dev / 'inputs/dev.inputs.jsonl')
    descriptor = dict(schema_version='comparison-retrieval-v1', source_manifest_sha256=sha_file(corpus / 'source-manifest.json'),
        inputs={key:sha_file(path) for key,path in source_inputs.items()}, code_sha256=sha_file(__file__),
        chunker_sha256=sha_file(ROOT / 'backend/apps/documents/processors/chunker.py'),
        packing_sha256=sha_file(Path(__file__).with_name('packing.py')),
        prompt_hashes={n:sha_file(ROOT / 'data/comparison' / n) for n in ('base-system.txt','rag-system.txt')},
        tokenizer_reference_sha256=sha_file(handoff / 'data/pilot-v2/tokenizer-reference.json'),
        model_id='BAAI/bge-m3', revision=REVISION, device='cpu', max_tokens=514)
    if index_source is not None:
        previous=Path(index_source)
        old=read_json(previous/'provenance.json')
        require(all(old[k]==descriptor[k] for k in ('source_manifest_sha256','chunker_sha256','model_id','revision','device','max_tokens')), 'REUSED_INDEX_SOURCE_OR_SPACE_CHANGED')
        pointer=read_json(previous/'index/current.json')
        descriptor['reused_index']=dict(path=str(previous.resolve()),
            snapshot_manifest_sha256=sha_file(previous/'index'/pointer['generation']/'manifest.json'),
            previous_provenance_sha256=sha_file(previous/'provenance.json'))
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'provenance.json').exists():
        require(read_json(output / 'provenance.json') == descriptor, 'PREPARATION_RESUME_DESCRIPTOR')
    else:
        write_json(output / 'provenance.json', descriptor)
    config = EmbeddingConfig(revision=REVISION, max_tokens=514, batch_size=2, device='cpu', local_files_only=True)
    chunk_config = ChunkingConfig(tokenizer_revision=REVISION, max_tokens=480, overlap_tokens=64)
    bge_tokenizer = AutoTokenizer.from_pretrained(config.model_id, revision=REVISION, local_files_only=True, trust_remote_code=False)
    chunks = []
    for source in registry['sources']:
        pdf = within(corpus, source['relative_path'])
        require(sha_file(pdf) == source['source_checksum'], 'SOURCE_PDF_CHANGED')
        pages = PdfReader(pdf).pages
        require(len(pages) == source['page_count'], 'SOURCE_PAGE_COUNT')
        envelope = dict(schema_version='1.0', **{k:source[k] for k in ('course_id','document_id','version_id')},
            checksum_sha256=source['source_checksum'], page_count=len(pages),
            pages=[dict(page_number=i+1, text=p.extract_text() or '') for i,p in enumerate(pages)])
        chunks.extend(asdict(c) for c in chunk_extraction(envelope, source['source_group_id'], chunk_config, bge_tokenizer))
    write_rows(output / 'source-chunks.jsonl', chunks)
    print(f'CHUNKED {len(chunks)} from {len(registry["sources"])} PDFs', flush=True)
    service = EmbeddingService(config)
    started = time.perf_counter()
    if index_source is not None:
        index=load_index(Path(index_source)/'index',config)
        require(index.export_chunks()==chunks,'REUSED_INDEX_CHUNK_MAPPING')
        print(f'REUSED VERIFIED FAISS: {index.count} vectors; no corpus re-embedding',flush=True)
    else:
        arrays, token_counts = [], []
        for start in range(0, len(chunks), 32):
            block = [dict(chunk_id=c['chunk_id'], text=c['text']) for c in chunks[start:start+32]]
            vectors, counts = embed_block(service, block, output / 'blocks' / f'corpus-{start:05}.npz', descriptor)
            arrays.append(vectors)
            token_counts.extend(counts.tolist())
            print(f'CORPUS {min(start+32,len(chunks))}/{len(chunks)} | {time.perf_counter()-started:.1f}s', flush=True)
        embedded = EmbeddedChunks(tuple(c['chunk_id'] for c in chunks), np.concatenate(arrays), tuple(token_counts), config.fingerprint())
        index = DenseIndex(chunks, embedded, config)
    if (output / 'index/current.json').exists():
        pointer = read_json(output / 'index/current.json')
        snapshot = output / 'index' / pointer['generation']
        require(read_json(snapshot / 'manifest.json')['index_sha256'] == __import__('hashlib').sha256(index.serialize()).hexdigest(), 'RESUMED_INDEX_CHANGED')
    else:
        snapshot = save_index(index, output / 'index', dict(purpose='isolated_comparison_not_live_authorization', provenance_sha256=digest(descriptor)))
    index_manifest = read_json(snapshot / 'manifest.json')
    reference = read_json(handoff / 'data/pilot-v2/tokenizer-reference.json')
    for name, info in reference['files'].items():
        asset = handoff / 'tokenizer' / name
        require(asset.stat().st_size == info['size_bytes'] and sha_file(asset) == info['sha256'], 'QWEN_TOKENIZER_BYTES')
    tokenizer = AutoTokenizer.from_pretrained(handoff / 'tokenizer', local_files_only=True, trust_remote_code=False)
    courses = {s['course_id']:s['course_code'] for s in registry['sources']}
    all_cases, query_vectors = [], {}
    for split in ('dev','main'):
        inputs, caches, models = read_rows(source_inputs[split]), [], []
        require(len(inputs) == (30 if split == 'dev' else 300), 'PREPARATION_CASE_COUNT')
        for position,item in enumerate(inputs):
            require(set(item) == {'qa_id','question','scope_id'}, 'GENERATOR_ALLOWLIST')
            start = time.perf_counter()
            query, _ = embed_block(service, [dict(chunk_id=item['qa_id'], text=item['question'])],
                output / 'blocks' / (item['qa_id'] + '.npz'), descriptor)
            embedding_seconds = time.perf_counter()-start
            query_vectors[item['qa_id']] = query[0]
            allowed = [i for i,c in enumerate(chunks) if c['course_id'] == item['scope_id']]
            require(bool(allowed), 'UNKNOWN_SCOPE')
            start = time.perf_counter()
            hits = index.search(query[0], top_k=5, row_ids=allowed)
            search_seconds = time.perf_counter()-start
            contexts = [dict(chunk_id=h['chunk_id'], rank=h['rank'], score=h['score'], text=h['text'],
                **{k:h['source'][k] for k in ('course_id','document_id','version_id','source_checksum','page_number','char_start','char_end')}) for h in hits]
            cache = pack_contexts(dict(**item, contexts=contexts, index_sha256=index_manifest['index_sha256'],
                query_embedding_seconds=embedding_seconds, search_seconds=search_seconds), tokenizer)
            validate_cache(cache)
            caches.append(cache)
            for arm in ('base','rag','tuned_rag'):
                messages = build_messages(cache, arm)
                ids = chat_tokens(tokenizer, messages)
                models.append(dict(qa_id=item['qa_id'], arm=arm, messages=messages, input_sha256=digest(messages),
                    contexts_sha256=None if arm == 'base' else cache['contexts_sha256'],
                    input_token_ids_sha256=digest(ids), input_tokens=len(ids)))
            if split == 'main':
                all_cases.append(dict(qa_id=item['qa_id'], course_code=courses[item['scope_id']], question=item['question']))
            if (position+1) % 10 == 0:
                print(f'{split.upper()} CACHE {position+1}/{len(inputs)}', flush=True)
        write_rows(output / (split+'.inputs.jsonl'), inputs)
        write_rows(output / (split+'.cache.jsonl'), caches)
        write_rows(output / (split+'.model-inputs.jsonl'), models)
        write_json(output / (split+'.schedule.json'), schedule(inputs))
    prior_path = corpus / 'semantic-screen/prior-questions.PRIVATE.jsonl'
    prior = read_rows(prior_path)
    vectors = [query_vectors[r['qa_id']] for r in all_cases]
    for start in range(0, len(prior), 32):
        block = [dict(chunk_id=r['qa_id'], text=r['question']) for r in prior[start:start+32]]
        result, _ = embed_block(service, block, output / 'blocks' / f'prior-{start:05}.npz', descriptor)
        vectors.extend(result)
        print(f'SEMANTIC PRIOR {min(start+32,len(prior))}/{len(prior)}', flush=True)
    matrix = np.asarray(vectors, dtype=np.float32)
    np.save(output / 'semantic-vectors.npy', matrix, allow_pickle=False)
    all_rows, findings = all_cases + prior, []
    for i,row in enumerate(all_cases):
        def nearest(indices):
            scores = [(float(matrix[i] @ matrix[j]), j) for j in indices if all_rows[j]['course_code'] == row['course_code'] and j != i]
            return [dict(**all_rows[j], cosine=score) for score,j in sorted(scores, reverse=True)[:3]]
        findings.append(dict(**row, nearest_main=nearest(range(300)), nearest_prior=nearest(range(300,len(all_rows))),
                             disposition='FRESH_SEMANTIC_TRIAGE_REQUIRES_CONTENT_REVIEW'))
    write_rows(output / 'semantic-findings.PRIVATE.jsonl', findings)
    write_json(output / 'semantic-report.json', dict(status='REAL_BGE_SCREEN_COMPLETED_NOT_APPROVAL',
        main=300, prior=len(prior), prior_questions_sha256=sha_file(prior_path), model=config.model_id,
        revision=REVISION, source_config=asdict(config), fresh_vectors=len(matrix)))
    write_json(output / 'build-report.json', dict(status='REAL_RETRIEVAL_REBUILT', documents=len(registry['sources']),
        physical_pages=sum(s['page_count'] for s in registry['sources']), chunks=len(chunks), embedding=asdict(config),
        chunking=asdict(chunk_config), wall_seconds=time.perf_counter()-started, qwen_inference=False, gpu_used=False,
        packages={n:version(n) for n in ('torch','transformers','sentence-transformers','faiss-cpu','pypdf')}))
    files = inventory(output)
    write_json(output / 'complete.json', dict(status='REAL_RETRIEVAL_AND_SEMANTIC_SCREEN_COMPLETE', files=files,
        main_authorized=False, model_generation_performed=False, provenance_sha256=digest(descriptor)))
    verify_inventory(output, files)
    print('PREPARATION_COMPLETE', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=ROOT / '.private/comparison/inputs/v3/evaluator/main')
    parser.add_argument('--benchmark', type=Path, default=ROOT / '.private/comparison/prepared/benchmark-v3')
    parser.add_argument('--dev', type=Path, default=ROOT / '.private/comparison/inputs/v3/generator/dev')
    parser.add_argument('--handoff', type=Path, default=ROOT / '.private/qlora/inputs/handoff')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--index-source', type=Path, help='Reuse an authenticated index with byte-identical source/chunk/config mapping, never reuse stale query caches')
    args = parser.parse_args()
    prepare(args.corpus, args.benchmark, args.dev, args.handoff, args.output,args.index_source)
