"""Join trusted per-version artifacts, checking aggregate metadata against each manifest."""
import json
from pathlib import Path
from .chunking import load_catalog
from .retrieval_contracts import ChunkingConfig
from .storage import private_path


def load_corpus_catalog(corpus_manifest):
    report = json.loads(Path(corpus_manifest).read_text(encoding='utf-8'))
    if report.get('schema_version') != '1.0' or not report.get('documents'):
        raise ValueError('Expected a nonempty W3 corpus manifest.')
    catalog, versions, config = {}, set(), None
    for row in report['documents']:
        manifest_path = private_path(row['manifest_key'])
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for field in ('course_id', 'document_id', 'version_id', 'source_checksum',
                      'page_count', 'chunk_count', 'chunks_key', 'chunks_checksum'):
            if row[field] != manifest[field]:
                raise ValueError('Corpus/version manifest mismatch: '+field)
        current = ChunkingConfig(**manifest['chunking_config'])
        if current.digest != report['config_hash'] or (config is not None and current != config):
            raise ValueError('Mixed chunking configurations in corpus.')
        config = current
        if row['version_id'] in versions:
            raise ValueError('Duplicate source version.')
        versions.add(row['version_id'])
        loaded = load_catalog(manifest_path)
        if catalog.keys() & loaded.keys():
            raise ValueError('Duplicate corpus chunk ID.')
        catalog.update(loaded)
    if len(versions) != report['document_count'] or len(catalog) != report['chunk_count']:
        raise ValueError('Corpus totals mismatch.')
    return catalog, config
