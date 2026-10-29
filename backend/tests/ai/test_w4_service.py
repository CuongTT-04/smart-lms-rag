from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
from datetime import timedelta
from django.utils import timezone
from apps.ai.services import answer_chat
from apps.documents.exceptions import DocumentError
from apps.courses.assessment_models import Assessment, AssessmentAttempt
from tests.documents.test_retrieval_scope import ScopeFixture


class ChatServiceTests(ScopeFixture):
    def setUp(self):
        super().setUp()
        self.data={'question': 'Câu hỏi?', 'mode':'qa', 'course_id':str(self.course.pk), 'session_id':str(self.session.pk)}
        self.output={'status':'ANSWERED', 'answer':'Nội dung [1].', 'references':[{'label':1, 'source_id':'S1'}], 'usage':None}
        self.runtime=SimpleNamespace(index=None, embedding=None, catalog={}, config={'timeout_seconds':60}, generate=Mock(return_value=self.output))
        self.hit={'chunk_id':'chunk-1', 'text':'Nguồn thật', 'source':{'document_id':str(self.doc.pk),
            'version_id':str(self.version.pk), 'document_title':'PDF', 'page_number':1, 'section_title':None}}
        self.retrieval=patch('apps.ai.services.retrieve_dense_authorized', return_value=[self.hit]).start()
        self.addCleanup(patch.stopall)

    def call(self):
        return answer_chat(user=self.student, data=self.data, runtime=self.runtime, request_id=str(uuid4()))

    def test_answer_maps_trusted_source_and_does_not_expose_context(self):
        result=self.call()
        self.assertEqual(result['citations'][0]['version_id'], str(self.version.pk))
        self.assertNotIn('text', result['citations'][0])
        self.assertEqual(result['citations'][0]['excerpt'], 'Nguồn thật')
        self.assertEqual(self.runtime.generate.call_args.kwargs['contexts'][0]['source_id'], 'S1')
        self.assertEqual(self.retrieval.call_args.kwargs['top_k'],5)

    def test_empty_scope_and_empty_hits_skip_generation(self):
        self.data['document_ids']=[]
        self.assertEqual(self.call()['status'], 'INSUFFICIENT_EVIDENCE')
        self.runtime.generate.assert_not_called()
        self.retrieval.assert_not_called()

    def test_history_retrieval_stays_within_query_limit_and_preserves_current_question(self):
        self.data['question'] = 'Q' * 8000
        history = [dict(question='Old topic', answer='Previous answer is not evidence')]
        self.runtime.generate.return_value = {**self.output, '_memory': dict(protocol='chat_history_v1')}
        answer_chat(user=self.student, data=self.data, runtime=self.runtime, request_id=str(uuid4()), history=history)
        query = self.retrieval.call_args.args[1]
        self.assertLessEqual(len(query), 8000)
        self.assertEqual(query, self.data['question'])
        self.assertEqual(self.runtime.generate.call_args.kwargs['history'], history)

    def test_unknown_citation_and_invalid_schema_fail_closed(self):
        for output in ({**self.output, 'references':[{'label':1,'source_id':'S999'}]},
                       {**self.output, 'answer':'[2]'}, {**self.output, 'references':[]},
                       {**self.output, 'status':'bad'}, {**self.output, 'usage':{'input_tokens':True,'output_tokens':1}},
                       {**self.output, 'answer':'['+'1'*5000+']'},
                       {**self.output, 'answer':123}):
            self.runtime.generate.return_value=output
            with self.assertRaises(DocumentError) as caught: self.call()
            self.assertEqual(caught.exception.code,'INVALID_GENERATION')

    def test_timeout_is_not_missing_evidence(self):
        self.runtime.generate.side_effect=TimeoutError('secret provider message')
        with self.assertRaises(DocumentError) as caught: self.call()
        self.assertEqual(caught.exception.code,'GENERATION_UNAVAILABLE')
        self.assertNotIn('secret',caught.exception.message)

    def test_model_limit_and_busy_errors_are_not_flattened_to_unavailable(self):
        for code,status in [('OUTPUT_LIMIT_REACHED',503),('GENERATION_TIMEOUT',503),('GENERATION_BUSY',429),('GENERATION_CONFIG_MISMATCH',503),('GENERATION_MISSING_CITATION',503)]:
            self.runtime.generate.side_effect=DocumentError(code,'Safe message',status)
            with self.assertRaises(DocumentError) as caught:self.call()
            self.assertEqual(caught.exception.code,code)

    def test_source_withdrawal_during_generation_prevents_answer(self):
        def generate(**kwargs):
            self.doc.is_published=False; self.doc.save()
            return self.output
        self.runtime.generate.side_effect=generate
        with self.assertRaises(DocumentError) as caught: self.call()
        self.assertEqual(caught.exception.code,'SCOPE_CHANGED')

    def test_test_started_during_generation_prevents_answer(self):
        def generate(**kwargs):
            assessment=Assessment.objects.create(session=self.session,title='Exam',kind='TEXT',mode='TEST',due_at=timezone.now()+timedelta(hours=1))
            AssessmentAttempt.objects.create(assessment=assessment,student=self.student,request_id=uuid4(),number=1,expires_at=assessment.due_at)
            return self.output
        self.runtime.generate.side_effect=generate
        with self.assertRaises(DocumentError) as caught: self.call()
        self.assertEqual(caught.exception.code,'AI_NOT_ALLOWED')
