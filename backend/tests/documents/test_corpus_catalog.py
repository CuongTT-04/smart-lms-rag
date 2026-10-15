import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from django.test import SimpleTestCase, override_settings
from apps.documents.chunking import build_version_chunks
from apps.documents.retrieval_contracts import ChunkingConfig
from tests.documents.test_chunker import CharacterTokenizer, envelope


class CorpusCatalogTests(SimpleTestCase):
    def test_load_verified_corpus_and_reject_aggregate_drift(self):
        from apps.documents.corpus_catalog import load_corpus_catalog
        with tempfile.TemporaryDirectory() as directory, override_settings(DOCUMENTS_STORAGE_ROOT=directory):
            root = Path(directory)
            data = envelope('actual page')
            (root/'extracted').mkdir()
            (root/'extracted/source.json').write_text(json.dumps(data), encoding='utf-8')
            config = ChunkingConfig(tokenizer_revision='test', max_tokens=32, overlap_tokens=4)
            version = SimpleNamespace(pk=data['version_id'], document_id=data['document_id'],
                document=SimpleNamespace(course_id=data['course_id'], removed_at=None, title='PDF'),
                checksum_sha256=data['checksum_sha256'], page_count=1, removed_at=None,
                status='EXTRACTED', extracted_storage_key='extracted/source.json')
            artifact = build_version_chunks(version, config, CharacterTokenizer())
            row = {**artifact, 'course_id': data['course_id'], 'document_id': data['document_id'],
                   'version_id': data['version_id'], 'source_checksum': data['checksum_sha256'], 'page_count': 1}
            report = {'schema_version': '1.0', 'config_hash': config.digest,
                      'documents': [row], 'document_count': 1, 'chunk_count': 1}
            path = root/'corpus.json'
            path.write_text(json.dumps(report), encoding='utf-8')
            catalog, loaded = load_corpus_catalog(path)
            self.assertEqual(len(catalog), 1)
            self.assertEqual(loaded, config)
            for field in ('source_checksum', 'chunks_checksum', 'course_id'):
                old = row[field]
                row[field] = 'wrong'
                path.write_text(json.dumps(report), encoding='utf-8')
                with self.subTest(field=field), self.assertRaises(ValueError):
                    load_corpus_catalog(path)
                row[field] = old
            report['documents'].append(row)
            path.write_text(json.dumps(report), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_corpus_catalog(path)
