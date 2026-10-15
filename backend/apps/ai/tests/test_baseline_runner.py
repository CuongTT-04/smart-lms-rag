"""CLI smoke with synthetic unit vectors, never a real corpus/model benchmark."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

from apps.documents.retrieval_contracts import Chunk, ChunkingConfig
from apps.ai.embeddings.base import EmbeddingConfig

ROOT = Path(__file__).resolve().parents[4]


class BaselineRunnerTests(unittest.TestCase):
    def test_corpus_runner_build_reload_metrics_and_error_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = root/'documents'
            storage.mkdir()
            config = ChunkingConfig(tokenizer_revision=EmbeddingConfig().revision)
            c = Chunk('1.0', 'unit-chunk', str(uuid4()), str(uuid4()), str(uuid4()),
                      'Fixture', 1, None, 0, 'unit text', 3, 0, 9, 'a'*64, config.digest)
            data = (json.dumps(asdict(c))+'\n').encode()
            (storage/'chunks.jsonl').write_bytes(data)
            manifest = {'schema_version': '1.0', 'version_id': c.version_id, 'document_id': c.document_id,
                'course_id': c.course_id, 'source_checksum': c.source_checksum, 'page_count': 1,
                'chunking_config': asdict(config), 'chunking_config_hash': config.digest,
                'chunk_count': 1, 'chunks_key': 'chunks.jsonl', 'chunks_checksum': hashlib.sha256(data).hexdigest()}
            (storage/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            corpus = {'schema_version': '1.0', 'documents': [{**manifest, 'manifest_key': 'manifest.json'}],
                      'document_count': 1, 'chunk_count': 1, 'config_hash': config.digest, 'probe_parser': 'unit_fixture'}
            (root/'corpus.json').write_text(json.dumps(corpus), encoding='utf-8')
            cases = [{'qa_id': 'fixture', 'course_id': c.course_id, 'question': 'unit question', 'mode': 'hint',
                      'gold_sources': [{'document_id': c.document_id, 'version_id': c.version_id, 'page_number': 1}]}]
            (root/'qa.json').write_text(json.dumps({'cases': cases}), encoding='utf-8')
            code = r'''
import importlib.util, sys
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from apps.ai.embeddings.base import EmbeddedChunks
from apps.ai.embeddings.service import EmbeddingService
spec = importlib.util.spec_from_file_location('baseline', sys.argv[1])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
vector = np.zeros(1024, dtype=np.float32); vector[0] = 1
def embed(self, records):
    return EmbeddedChunks(tuple(r['chunk_id'] for r in records), np.repeat(vector[None,:],len(records),axis=0),
                          (5,)*len(records),self.config.fingerprint())
model = SimpleNamespace(tokenizer=SimpleNamespace(num_special_tokens_to_add=lambda **kwargs: 2))
fail = sys.argv[2] == 'fail'
with patch.object(EmbeddingService, '_load_model', return_value=model), \
     patch.object(EmbeddingService, 'embed_chunks', embed), \
     patch.object(EmbeddingService, 'runtime_info', return_value={'unit_vector_stub': True}), \
     patch.object(EmbeddingService, 'embed_query', side_effect=RuntimeError('unit failure') if fail else None, return_value=vector):
    module.main(sys.argv[3:])
'''
            for fail in (False, True):
                output = root/('error' if fail else 'ok')
                args = [sys.executable, '-c', code, str(ROOT/'scripts/run_w3_baseline.py'), 'fail' if fail else 'ok',
                        '--corpus-manifest', str(root/'corpus.json'), '--storage-root', str(storage),
                        '--qa', str(root/'qa.json'), '--config', str(ROOT/'backend/config/w3/embedding_config.json'),
                        '--output-dir', str(output)]
                completed = subprocess.run(args, capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                metrics = json.loads((output/'metrics.json').read_text())
                self.assertEqual(metrics['scored_qa'], 1)
                self.assertEqual(metrics['retrieval_error_qa'], int(fail))
                self.assertEqual(metrics['page_recall']['5'], 0 if fail else 1)
                self.assertFalse(metrics['authorization_verified'])
                self.assertTrue((output/'index/current.json').is_file())
                self.assertEqual(metrics['provenance']['reload_checks'], 0 if fail else 1)
            # Exercise actual persisted snapshot on a fresh process, same config/catalog.
            args[args.index('fail')] = 'ok'
            args[args.index(str(root/'error'))] = str(root/'ok')
            completed = subprocess.run([*args, '--reuse-index'], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
