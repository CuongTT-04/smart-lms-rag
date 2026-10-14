import json
import tempfile
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace
from django.test import SimpleTestCase, override_settings
from apps.documents.chunking import build_version_chunks, load_catalog
from apps.documents.retrieval_contracts import ChunkingConfig
from tests.documents.test_chunker import CharacterTokenizer, envelope


class BatchChunkTests(SimpleTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.settings=override_settings(DOCUMENTS_STORAGE_ROOT=self.root)
        self.settings.enable();self.addCleanup(self.settings.disable)
        self.data=envelope('a'*120,'Page two')
        self.version=SimpleNamespace(pk=self.data['version_id'], document_id=self.data['document_id'],
            document=SimpleNamespace(course_id=self.data['course_id'],removed_at=None,title='PDF'),
            checksum_sha256=self.data['checksum_sha256'],page_count=2,removed_at=None,
            status='EXTRACTED',extracted_storage_key='extracted/source.json')
        (self.root/'extracted').mkdir()
        self.write_source()
        self.config=ChunkingConfig(tokenizer_revision='test',max_tokens=32,overlap_tokens=4)

    def write_source(self):
        (self.root/'extracted/source.json').write_text(json.dumps(self.data),encoding='utf-8')

    def test_atomic_idempotent_artifact_and_verified_catalog(self):
        first=build_version_chunks(self.version,self.config,CharacterTokenizer())
        self.assertEqual(first,build_version_chunks(self.version,self.config,CharacterTokenizer()))
        manifest=json.loads((self.root/first['manifest_key']).read_text())
        catalog=load_catalog(self.root/first['manifest_key'])
        self.assertEqual(len(catalog),manifest['chunk_count'])
        self.assertFalse(list(self.root.rglob('*.tmp')))
        self.assertEqual(self.version.status,'EXTRACTED')
        (self.root/manifest['chunks_key']).write_text('tampered',encoding='utf-8')
        with self.assertRaises(ValueError):load_catalog(self.root/first['manifest_key'])

    def test_reject_metadata_mismatch_removed_and_empty_output(self):
        for field in ['course_id','document_id','version_id','checksum_sha256']:
            old=self.data[field];self.data[field]=str(uuid4()) if field!='checksum_sha256' else 'b'*64
            self.write_source()
            with self.assertRaises(ValueError):build_version_chunks(self.version,self.config,CharacterTokenizer())
            self.data[field]=old
        self.write_source();self.version.removed_at=True
        with self.assertRaises(ValueError):build_version_chunks(self.version,self.config,CharacterTokenizer())
        self.version.removed_at=None;self.data['pages'][0]['text']='';self.data['pages'][1]['text']=''
        self.write_source()
        with self.assertRaises(ValueError):build_version_chunks(self.version,self.config,CharacterTokenizer())
