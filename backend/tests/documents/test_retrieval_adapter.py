from dataclasses import replace
from unittest.mock import Mock
from apps.documents.exceptions import DocumentError
from apps.documents.retrieval_contracts import Chunk
from apps.documents.retrieval_scope import resolve_scope
from apps.documents.retrieval_adapter import retrieve_authorized
from tests.documents.test_retrieval_scope import ScopeFixture


class AdapterTests(ScopeFixture):
    # Setup fixture reused; scope tests are already exercised in their own module.
    def setUp(self):
        super().setUp()
        self.chunk=Chunk('1.0','chunk-1',str(self.course.pk),str(self.doc.pk),str(self.version.pk),
            'PDF',1,None,0,'Trusted text',3,0,12,'a'*64,'b'*64)
        self.catalog={'chunk-1':self.chunk}
        self.scope=resolve_scope(self.student,self.course.pk,session_id=self.session.pk)
        self.retriever=Mock();self.retriever.search.return_value=[{'chunk_id':'chunk-1','score':0.72,'text':'FORGED'}]

    def test_response_uses_trusted_catalog_and_no_storage_path(self):
        result=retrieve_authorized(self.student,'Question',self.scope,self.retriever,catalog=self.catalog)
        self.assertEqual(result[0]['text'],'Trusted text')
        self.assertEqual(result[0]['source']['page_number'],1)
        self.assertNotIn('storage_key',str(result))

    def test_bad_provider_unknown_duplicate_nan_and_wrong_provenance_fail_closed(self):
        cases=[[{'chunk_id':'unknown','score':1}],
               [{'chunk_id':'chunk-1','score':float('nan')}],
               [{'chunk_id':'chunk-1','score':1}]*2]
        for hits in cases:
            self.retriever.search.return_value=hits
            with self.assertRaises(DocumentError):retrieve_authorized(self.student,'Q',self.scope,self.retriever,catalog=self.catalog)
        self.retriever.search.return_value=[{'chunk_id':'chunk-1','score':1}]
        with self.assertRaises(DocumentError):retrieve_authorized(self.student,'Q',self.scope,self.retriever,
            catalog={'chunk-1':replace(self.chunk,source_checksum='c'*64)})

    def test_scope_forgery_and_empty_scope_never_search(self):
        with self.assertRaises(DocumentError):retrieve_authorized(self.student,'Q',replace(self.scope,allowed_version_ids=()),self.retriever,catalog=self.catalog)
        self.retriever.search.assert_not_called()
        empty=resolve_scope(self.student,self.course.pk,document_ids=[])
        self.assertEqual(retrieve_authorized(self.student,'Q',empty,self.retriever,catalog={}),[])
        self.retriever.search.assert_not_called()

    def test_permission_revoked_or_document_removed_during_search_is_blocked(self):
        def revoke(**kwargs):
            self.member.status='REMOVED';self.member.save();return [{'chunk_id':'chunk-1','score':1}]
        self.retriever.search.side_effect=revoke
        with self.assertRaises(DocumentError):retrieve_authorized(self.student,'Q',self.scope,self.retriever,catalog=self.catalog)
        self.member.status='ACTIVE';self.member.save()
        def remove(**kwargs):
            from django.utils import timezone
            self.doc.removed_at=timezone.now();self.doc.save();return [{'chunk_id':'chunk-1','score':1}]
        self.retriever.search.side_effect=remove
        with self.assertRaises(DocumentError):retrieve_authorized(self.student,'Q',self.scope,self.retriever,catalog=self.catalog)

    def test_invalid_query_topk_and_index_failure(self):
        for query,k in [('',5),('Q',True),('Q',0),('Q',11)]:
            with self.assertRaises(DocumentError):retrieve_authorized(self.student,query,self.scope,self.retriever,top_k=k,catalog=self.catalog)
        self.retriever.search.side_effect=RuntimeError('private secret path')
        with self.assertRaises(DocumentError) as caught:retrieve_authorized(self.student,'Q',self.scope,self.retriever,catalog=self.catalog)
        self.assertEqual(caught.exception.code,'RETRIEVAL_UNAVAILABLE')
        self.assertNotIn('private secret',str(caught.exception))

    def test_provider_malformed_id_and_huge_score_are_controlled_errors(self):
        for hit in [{'chunk_id':[],'score':1},{'chunk_id':{},'score':1},
                    {'chunk_id':'chunk-1','score':10**1000}]:
            self.retriever.search.return_value=[hit]
            with self.assertRaises(DocumentError) as caught:
                retrieve_authorized(self.student,'Q',self.scope,self.retriever,catalog=self.catalog)
            self.assertEqual(caught.exception.code,'INVALID_RETRIEVAL')

    def test_publication_change_while_searching_blocks_old_source(self):
        def unpublish(**kwargs):
            self.doc.is_published=False;self.doc.save()
            return [{'chunk_id':'chunk-1','score':1}]
        self.retriever.search.side_effect=unpublish
        with self.assertRaises(DocumentError):
            retrieve_authorized(self.student,'Q',self.scope,self.retriever,catalog=self.catalog)
