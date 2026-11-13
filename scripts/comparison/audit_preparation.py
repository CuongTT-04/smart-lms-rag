"""Read back fresh retrieval with the pinned inference tokenizer, without Qwen weights."""
import argparse
from importlib.metadata import version
from pathlib import Path

from scripts.comparison.packing import evidence_tokens, schedule
from scripts.comparison.protocol import digest, read_rows, write_json
from scripts.comparison.runner import audit_assets, validate_inputs
from scripts.qlora.data import read_json, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory


def check_context(cache, chunks):
    retrieved = cache['packing']['retrieved_chunks']
    require(0 < len(retrieved) <= 5, 'RETRIEVED_TOP_K')
    for item in retrieved:
        source = chunks[item['chunk_id']]
        require(source['course_id'] == cache['scope_id'], 'CROSS_COURSE_RETRIEVAL')
        require(item['document_id'] == source['document_id']
                and item['page_number'] == source['page_number']
                and item['text_sha256'] == digest(source['text']), 'RETRIEVED_SOURCE_BINDING')
    require([c['chunk_id'] for c in cache['contexts']] == [r['chunk_id'] for r in retrieved[:len(cache['contexts'])]], 'PACKING_RANK_ORDER')
    for rank, context in enumerate(cache['contexts'], 1):
        source = chunks[context['chunk_id']]
        require(context['rank'] == rank and context['text'].strip()
                and source['text'].startswith(context['text']), 'PACKING_NOT_SOURCE_PREFIX')
        require(all(context[k] == source[k] for k in ('course_id','document_id','version_id',
                    'source_checksum','page_number','char_start','char_end')), 'CONTEXT_SOURCE_METADATA')
        if context['text'] != source['text']:
            require(rank == len(cache['contexts']) and context['packed_char_end'] == source['char_start']+len(context['text']), 'PACKED_END')


def audit(retrieval, package):
    complete = read_json(retrieval/'complete.json')
    verify_inventory(retrieval, complete['files'])
    require(inventory(retrieval, ('complete.json',)) == complete['files'], 'RETRIEVAL_INVENTORY')
    verify_inventory(package, read_json(package/'manifest.json')['files'])
    tokenizer, assets = audit_assets(package, read_json(package/'run-config.json'))
    reference = read_json(package/'tokenizer-reference.json')
    for name, expected in reference['packages'].items():
        require(version(name) == expected, 'AUDIT_TOKENIZER_LIBRARY_PIN:'+name)
    chunks = {r['chunk_id']:r for r in read_rows(retrieval/'source-chunks.jsonl')}
    require(len(chunks) == 1131, 'CURRENT_CHUNK_COUNT')
    pointer = read_json(retrieval/'index/current.json')
    index = read_json(retrieval/'index'/pointer['generation']/'manifest.json')
    result = {}
    for split, count in (('dev',30), ('main',300)):
        inputs, caches, models = [read_rows(retrieval/(split+'.'+name+'.jsonl')) for name in ('inputs','cache','model-inputs')]
        require(len(inputs) == count and len(models) == count*3, 'SPLIT_COUNTS')
        validate_inputs(inputs, caches, models, tokenizer)
        require(read_json(retrieval/(split+'.schedule.json')) == schedule(inputs), 'SCHEDULE_CHANGED')
        for cache in caches:
            check_context(cache, chunks)
            require(cache['index_sha256'] == index['index_sha256'], 'CACHE_INDEX_BINDING')
            require(evidence_tokens(tokenizer, cache['contexts']) == cache['packing']['evidence_tokens'] <= 3072, 'EVIDENCE_TOKEN_BUDGET')
        result[split] = dict(cases=len(inputs), model_inputs=len(models),
            max_input_tokens=max(r['input_tokens'] for r in models),
            max_evidence_tokens=max(c['packing']['evidence_tokens'] for c in caches),
            packed_cases=sum(c['packing']['truncated'] for c in caches))
    return dict(status='FRESH_CACHE_AND_990_PINNED_TOKENIZER_INPUTS_PASSED',
        retrieval_complete_sha256=sha_file(retrieval/'complete.json'),
        package_manifest_sha256=sha_file(package/'manifest.json'),
        chunks=len(chunks), index_sha256=index['index_sha256'], splits=result,
        tokenizer_packages=reference['packages'], assets=assets, qwen_generation=False,
        training=False, main_authorized=False,
        semantic_screen='COMPLETED_CONTENT_REVIEW_RECORDED_SEPARATELY',
        live_backend_index_modified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrieval', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'NEW_AUDIT_OUTPUT_REQUIRED')
    report = audit(args.retrieval, args.package)
    write_json(args.output, report)
    print(report['status'])
