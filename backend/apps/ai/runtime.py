"""Operator-configured runtime, loaded once per process; no fallback model or mock."""
from dataclasses import dataclass
from functools import lru_cache
import json
import math
import os
from pathlib import Path
from collections.abc import Callable
from django.conf import settings
from django.utils.module_loading import import_string
from apps.documents.exceptions import DocumentError


@dataclass(frozen=True)
class ChatRuntime:
    index: object
    embedding: object
    catalog: dict
    config: dict
    generate: Callable


def setting(name, default=''):
    return getattr(settings, name, os.environ.get(name, default))


def get_runtime():
    # Refresh when the worker atomically replaces current.json, without reloading
    # BGE weights for each snapshot or restarting HTTP workers.
    try:
        paths=[setting('AI_GENERATION_CONFIG'),setting('AI_EMBEDDING_CONFIG'),
            str(Path(setting('AI_INDEX_DIRECTORY'))/'current.json')]
        import hashlib
        revision=hashlib.sha256()
        revision.update(str((paths,setting('AI_GENERATOR'),setting('AI_CATALOG_MANIFESTS'))).encode())
        for path in paths:revision.update(Path(path).read_bytes())
    except (OSError,ValueError):
        return _load_runtime('not-ready')
    return _load_runtime(revision.hexdigest())


@lru_cache(maxsize=1)
def _embedding_service(config_json):
    from apps.ai.embeddings.base import EmbeddingConfig
    from apps.ai.embeddings.service import EmbeddingService
    return EmbeddingService(EmbeddingConfig(**json.loads(config_json)))


@lru_cache(maxsize=2)
def _load_runtime(revision):
    generator_path = setting('AI_GENERATOR')
    config_path = setting('AI_GENERATION_CONFIG')
    if not generator_path or not config_path:
        raise DocumentError('GENERATION_UNAVAILABLE', 'Trợ lý AI chưa được cấu hình mô hình.', 503)
    try:
        generate = import_string(generator_path)
        config = json.loads(Path(config_path).read_text(encoding='utf-8'))
        if not callable(generate) or not config.get('model') or not config.get('prompt_version'):
            raise ValueError('Missing model/prompt')
        for key in ('max_input_tokens', 'max_output_tokens'):
            if type(config[key]) is not int or config[key] < 1:
                raise ValueError(key)
        timeout = config['timeout_seconds']
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 90:
            raise ValueError('timeout')
        temperature = config['temperature']
        if type(temperature) not in (int, float) or not math.isfinite(temperature) or not 0 <= temperature <= 2:
            raise ValueError('temperature')
    except Exception as exc:
        raise DocumentError('GENERATION_UNAVAILABLE', 'Không thể nạp cấu hình mô hình AI.', 503) from exc
    try:
        from apps.ai.embeddings.base import EmbeddingConfig
        from apps.ai.embeddings.service import EmbeddingService
        from apps.ai.retrieval.storage import load_index
        from apps.documents.chunking import load_catalog
        embedding_path = setting('AI_EMBEDDING_CONFIG')
        index_path = setting('AI_INDEX_DIRECTORY')
        manifests = setting('AI_CATALOG_MANIFESTS')
        if not embedding_path or not index_path or not manifests:
            raise ValueError('Missing index/catalog configuration')
        embedding_config = EmbeddingConfig.from_file(embedding_path)
        pointer_path=Path(index_path)/'current.json'
        pointer_bytes=pointer_path.read_bytes()
        index = load_index(index_path, embedding_config)
        if manifests=='@index':
            from apps.documents.storage import private_path
            pointer=json.loads(pointer_bytes)
            manifest=json.loads((Path(index_path)/pointer['generation']/'manifest.json').read_bytes())
            keys=manifest['metadata']['catalog_manifest_keys']
            if not isinstance(keys,dict) or not keys:raise ValueError('Missing catalog manifest keys')
            manifest_paths=[private_path(key) for key in keys.values()]
        else:
            manifest_paths=manifests.split(os.pathsep)
        catalog = {}
        for manifest in manifest_paths:
            records = load_catalog(manifest)
            if set(records) & set(catalog):
                raise ValueError('Duplicate catalog ID')
            catalog.update(records)
        from dataclasses import asdict
        rows = index.export_chunks()
        if len(rows) != len(catalog) or any(asdict(catalog[row['chunk_id']]) != row for row in rows):
            raise ValueError('Index/catalog mismatch')
        if pointer_path.read_bytes()!=pointer_bytes:raise ValueError('Index changed during load; retry')
        return ChatRuntime(index, _embedding_service(json.dumps(embedding_config.__dict__,sort_keys=True)), catalog, config, generate)
    except Exception as exc:
        raise DocumentError('RETRIEVAL_UNAVAILABLE', 'Chỉ mục học liệu chưa sẵn sàng.', 503) from exc


get_runtime.cache_clear = _load_runtime.cache_clear
