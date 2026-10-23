"""Real FAISS + PostgreSQL permissions, deterministic embedding and generation.

This is integration coverage, NOT evidence of a real LLM/BGE quality run.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
from dataclasses import asdict
import numpy as np
from apps.ai.embeddings.base import EmbeddingConfig, EmbeddedChunks
from apps.ai.retrieval.index import DenseIndex
from apps.ai.services import answer_chat
from apps.documents.retrieval_contracts import Chunk
from apps.documents.exceptions import DocumentError
from tests.documents.test_retrieval_scope import ScopeFixture


class ChatDenseIntegrationTests(ScopeFixture):
    def setUp(self):
        super().setUp()
        config=EmbeddingConfig(max_tokens=514)
        chunk=Chunk('1.0','w4-chunk',str(self.course.pk),str(self.doc.pk),str(self.version.pk),
            'PDF',1,None,0,'Trusted source',3,0,14,'a'*64,'b'*64)
        vector=np.zeros((1,1024),dtype=np.float32); vector[0,0]=1
        index=DenseIndex([asdict(chunk)],EmbeddedChunks((chunk.chunk_id,),vector,(3,),config.fingerprint()),config)
        from apps.ai.embeddings.service import EmbeddingService
        embedding=EmbeddingService(config)
        self.patch=patch.object(embedding,'embed_query',return_value=vector[0])
        self.patch.start();self.addCleanup(self.patch.stop)
        self.runtime=SimpleNamespace(index=index,embedding=embedding,catalog={chunk.chunk_id:chunk},
            config={'timeout_seconds':60},generate=Mock(return_value={'status':'ANSWERED','answer':'Nội dung [1]',
            'references':[{'label':1,'source_id':'S1'}],'usage':None}))
        self.data={'question':'Nội dung?', 'mode':'qa','course_id':str(self.course.pk),'session_id':str(self.session.pk)}

    def call(self):
        return answer_chat(user=self.student,data=self.data,runtime=self.runtime,request_id=str(uuid4()))

    def test_real_index_and_bridge_preserve_source_ids(self):
        response=self.call()
        self.assertEqual(response['citations'][0]['chunk_id'],'w4-chunk')
        self.assertEqual(response['citations'][0]['version_id'],str(self.version.pk))

    def test_revoked_enrollment_does_not_call_model(self):
        self.enrollment.status='WITHDRAWN';self.enrollment.save()
        with self.assertRaises(DocumentError):self.call()
        self.runtime.generate.assert_not_called()

    def test_empty_selection_does_not_search_index_or_call_model(self):
        self.data['document_ids']=[]
        self.assertEqual(self.call()['status'],'INSUFFICIENT_EVIDENCE')
        self.runtime.generate.assert_not_called()

    def test_index_catalog_mismatch_is_service_error(self):
        self.runtime.catalog={}
        with self.assertRaises(DocumentError) as caught:self.call()
        self.assertEqual(caught.exception.code,'RETRIEVAL_UNAVAILABLE')
        self.runtime.generate.assert_not_called()

    def test_preflight_checks_provenance_without_claiming_llm_run(self):
        from io import StringIO
        import json
        from django.core.management import call_command
        self.runtime.config['model']='test-double-not-a-real-model'
        output=StringIO()
        with patch('apps.ai.management.commands.check_w4_chat_runtime.get_runtime',return_value=self.runtime):
            call_command('check_w4_chat_runtime',stdout=output)
        report=json.loads(output.getvalue())
        self.assertEqual(report['status'],'CONFIGURED_NOT_MODEL_VERIFIED')
        self.assertFalse(report['llm_verified'])
        self.assertEqual(report['mismatched_chunk_count'],0)
        self.runtime.generate.assert_not_called()
