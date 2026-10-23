import hashlib
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
import numpy as np
from django.test import override_settings
from apps.documents.models import IngestionJob, DocumentVersion
from apps.documents.indexing import enqueue_missing, claim_index_job, process_index_job, prune_index
from apps.documents.storage import private_path
from apps.documents.services import remove_document
from apps.ai.embeddings.base import EmbeddedChunks, EmbeddingConfig
from apps.ai.retrieval.storage import load_index
from apps.documents.retrieval_contracts import ChunkingConfig
from tests.documents.test_retrieval_scope import ScopeFixture


class Tokenizer:
    def __call__(self, text, **kwargs):
        return {'offset_mapping': [(i,i+1) for i in range(len(text))]}
    def encode(self, text, **kwargs):
        return list(range(len(text)))


class FakeEmbedding:
    def __init__(self, config):
        self.config=config; self.calls=0
    def embed_chunks(self, records):
        self.calls+=len(records)
        vectors=np.zeros((len(records),1024),dtype=np.float32)
        for i,r in enumerate(records): vectors[i,int(hashlib.sha256(r['text'].encode()).hexdigest(),16)%1024]=1
        return EmbeddedChunks(tuple(r['chunk_id'] for r in records),vectors,tuple(len(r['text'])+2 for r in records),self.config.fingerprint())


class AutomaticIndexTests(ScopeFixture):
    def setUp(self):
        super().setUp()
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.config=EmbeddingConfig(max_tokens=34)
        self.chunk_config=ChunkingConfig(tokenizer_revision=self.config.revision,max_tokens=32,overlap_tokens=4)
        config_path=Path(self.tmp.name)/'embedding.json';config_path.write_text(json.dumps(asdict(self.config)))
        self.override=override_settings(DOCUMENTS_STORAGE_ROOT=Path(self.tmp.name)/'private',
            AI_EMBEDDING_CONFIG=str(config_path),AI_INDEX_DIRECTORY=str(Path(self.tmp.name)/'index'))
        self.override.enable();self.addCleanup(self.override.disable)
        self.embedding=FakeEmbedding(self.config)
        self.prepare(self.version,'First source sentence.')

    def prepare(self, version, text):
        original=private_path(version.original_storage_key);original.parent.mkdir(parents=True,exist_ok=True)
        original.write_bytes(text.encode());version.checksum_sha256=hashlib.sha256(text.encode()).hexdigest()
        version.extracted_storage_key=f'extracted/{version.pk}/test.json'
        extraction=private_path(version.extracted_storage_key);extraction.parent.mkdir(parents=True,exist_ok=True)
        extraction.write_text(json.dumps({'schema_version':'1.0','course_id':str(self.course.pk),
            'document_id':str(version.document_id),'version_id':str(version.pk),
            'checksum_sha256':version.checksum_sha256,'page_count':1,'pages':[{'page_number':1,'text':text}]}))
        version.save()

    def process(self):
        enqueue_missing(self.config,self.chunk_config)
        job=claim_index_job()
        self.assertIsNotNone(job)
        process_index_job(job,self.embedding,Tokenizer(),self.chunk_config)
        job.refresh_from_db();return job

    def test_backfill_durable_idempotent_and_marks_ready(self):
        job=self.process();self.assertEqual(job.status,'SUCCEEDED')
        self.version.refresh_from_db();self.assertEqual(self.version.status,'READY')
        self.assertIsNotNone(self.version.indexed_at)
        enqueue_missing(self.config,self.chunk_config)
        self.assertIsNone(claim_index_job())
        self.assertEqual(IngestionJob.objects.filter(job_type='INDEX').count(),1)
        index=load_index(Path(self.tmp.name)/'index',self.config)
        self.assertEqual(index.export_chunks()[0]['version_id'],str(self.version.pk))

    def test_second_version_reuses_old_vectors_and_keeps_published_version(self):
        self.process();first=self.embedding.calls
        newer=DocumentVersion.objects.create(document=self.doc,version_number=2,file_name='b.pdf',
            file_size_bytes=20,original_storage_key='b.pdf',checksum_sha256='b'*64,page_count=1,status='EXTRACTED')
        self.prepare(newer,'Second source.')
        self.process()
        self.assertEqual(self.embedding.calls,first+1)
        self.doc.refresh_from_db();self.assertEqual(self.doc.published_version_id,self.version.pk)
        index=load_index(Path(self.tmp.name)/'index',self.config)
        self.assertEqual({r['version_id'] for r in index.export_chunks()},{str(newer.pk),str(self.version.pk)})

    def test_index_failure_keeps_extracted_pdf_and_previous_snapshot(self):
        enqueue_missing(self.config,self.chunk_config);job=claim_index_job()
        with patch.object(self.embedding,'embed_chunks',side_effect=RuntimeError('private text')):
            process_index_job(job,self.embedding,Tokenizer(),self.chunk_config)
        job.refresh_from_db();self.version.refresh_from_db()
        self.assertEqual(job.status,'FAILED');self.assertEqual(self.version.status,'EXTRACTED')
        self.assertIsNone(self.version.indexed_at)
        self.assertNotIn('private',job.error_code)

    def test_removal_during_embedding_cannot_publish_or_revive(self):
        original=self.embedding.embed_chunks
        def remove(records):
            result=original(records);remove_document(self.owner,self.doc);return result
        with patch.object(self.embedding,'embed_chunks',side_effect=remove):
            self.process()
        self.version.refresh_from_db();self.assertEqual(self.version.status,'REMOVED')
        self.assertFalse((Path(self.tmp.name)/'index/current.json').exists())

    def test_prune_removed_document_and_rename_reuses_vectors(self):
        self.process();before=self.embedding.calls
        self.doc.title='New title';self.doc.save()
        self.process();self.assertEqual(self.embedding.calls,before)
        self.assertEqual(load_index(Path(self.tmp.name)/'index',self.config).export_chunks()[0]['document_title'],'New title')
        remove_document(self.owner,self.doc)
        prune_index(self.config)
        self.assertTrue(json.loads((Path(self.tmp.name)/'index/current.json').read_text())['empty'])

    def test_http_runtime_refreshes_snapshot_but_reuses_embedding_service(self):
        from apps.ai.runtime import get_runtime
        self.process()
        generation=Path(self.tmp.name)/'generation.json'
        generation.write_text(json.dumps({'model':'Qwen/Qwen2.5-7B-Instruct','prompt_version':'bounded_guidance',
            'max_input_tokens':3584,'max_output_tokens':256,'timeout_seconds':30,'temperature':0.0}))
        with override_settings(AI_GENERATOR='apps.ai.remote.generate_answer',AI_GENERATION_CONFIG=str(generation),
                               AI_CATALOG_MANIFESTS='@index'):
            first=get_runtime()
            self.doc.title='Updated';self.doc.save();self.process()
            second=get_runtime()
            self.assertIsNot(first.index,second.index)
            self.assertIs(first.embedding,second.embedding)
            self.assertEqual({c.document_title for c in second.catalog.values()},{'Updated'})
        get_runtime.cache_clear()

    def test_rename_back_to_previous_title_republishes_old_digest(self):
        self.process();before=self.embedding.calls
        title=self.doc.title
        self.doc.title='B';self.doc.save();self.process()
        self.doc.title=title;self.doc.save();self.process()
        self.assertEqual(self.embedding.calls,before)
        self.assertEqual({r['document_title'] for r in load_index(Path(self.tmp.name)/'index',self.config).export_chunks()},{title})

    def test_claim_locks_document_before_version_before_job(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        enqueue_missing(self.config,self.chunk_config)
        with CaptureQueriesContext(connection) as queries:
            self.assertIsNotNone(claim_index_job())
        locks=[q['sql'] for q in queries.captured_queries if 'FOR UPDATE' in q['sql']]
        self.assertIn('documents_knowledgedocument',locks[0])
        self.assertIn('documents_documentversion',locks[1])
        self.assertIn('documents_ingestionjob',locks[2])

    def test_index_only_retry_does_not_reextract_pdf(self):
        from apps.documents.services import retry_ingestion
        enqueue_missing(self.config,self.chunk_config);job=claim_index_job()
        with patch.object(self.embedding,'embed_chunks',side_effect=RuntimeError('temporary')):
            process_index_job(job,self.embedding,Tokenizer(),self.chunk_config)
        self.version.watermark_status='READY';self.version.watermarked_view_key='views/test.pdf'
        self.version.save();view=private_path('views/test.pdf');view.parent.mkdir(parents=True,exist_ok=True);view.write_bytes(b'pdf')
        first=retry_ingestion(self.owner,self.doc,self.version,'index-retry')
        second=retry_ingestion(self.owner,self.doc,self.version,'index-retry')
        self.assertEqual(first.job_id,job.pk);self.assertEqual(first.pk,second.pk)
        self.version.refresh_from_db();self.assertEqual(self.version.status,'EXTRACTED')
