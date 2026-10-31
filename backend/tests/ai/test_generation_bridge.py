from dataclasses import asdict
from django.test import SimpleTestCase
from apps.ai.tests import test_rag_pipeline as fixtures
from apps.ai.rag import GenerationConfig, RAGPipeline
from apps.ai.integration import GenerationBridge
from apps.documents.exceptions import DocumentError


class GenerationBridgeTests(SimpleTestCase):
    def setUp(self):
        self.provider=fixtures.FakeProvider()
        fixture=fixtures.RAGPipelineTests();fixture.setUp()
        self.context=asdict(fixture.first)
        self.bridge=GenerationBridge(RAGPipeline(self.provider,GenerationConfig(model=self.provider.config,prompt_version='frozen_baseline')))

    def call(self, **extra):
        return self.bridge(**{**dict(question='Nội dung tài liệu?',mode='qa',contexts=[self.context],exercise=None,config={}),**extra})

    def test_application_dict_output_from_real_pipeline(self):
        result=self.call()
        self.assertEqual(set(result),{'status','answer','references','usage'})
        self.assertEqual(result['references'],[{'label':1,'source_id':'S1'}])
        self.assertEqual(self.provider.generate_calls,1)

    def test_conversation_bridge_passes_history_into_real_prompt_builder(self):
        result = self.call(question='Giải thích ý vừa nêu?',history=[{'question':'Chủ đề trước?', 'answer':'Câu trả lời trước [9]'}])
        self.assertEqual(result['_memory']['protocol'],'chat_history_v1')
        self.assertEqual(result['_memory']['turns_used'],1)
        self.assertEqual([m['role'] for m in self.provider.messages],['system','user','assistant','user'])
        self.assertNotIn('[9]',self.provider.messages[2]['content'])

    def test_hint_translates_visible_exercise_and_hides_answer_fields(self):
        self.provider.text='READ [1]'
        exercise={'assessment_id':'a1','title':'Ôn tập','description':'Đề bài', 'kind':'QUIZ',
            'question':{'id':'q1','prompt':'Câu hỏi?', 'choices':[{'id':'a','text':'A'}], 'correct_ids':['a']}}
        with self.assertRaises(DocumentError):
            self.bridge(question='Gợi ý?',mode='hint',contexts=[self.context],exercise=exercise,config={})
        del exercise['question']['correct_ids']
        result=self.bridge(question='Gợi ý?',mode='hint',contexts=[self.context],exercise=exercise,config={})
        self.assertEqual(result['status'],'ANSWERED')
        self.assertNotIn('correct_ids',str(self.provider.messages))

    def test_provider_failure_is_not_a_successful_answer(self):
        from apps.ai.providers import GenerationError
        self.provider.failure=GenerationError('GENERATION_TIMEOUT','Timeout')
        with self.assertRaises(DocumentError) as caught:self.call()
        self.assertEqual(caught.exception.code,'GENERATION_UNAVAILABLE')

    def test_missing_and_unknown_citations_have_specific_public_errors(self):
        for text, code in [('Answer without source', 'GENERATION_MISSING_CITATION'), ('Answer [9]', 'GENERATION_INVALID_CITATION')]:
            self.provider.text=text
            with self.assertRaises(DocumentError) as caught: self.call()
            self.assertEqual(caught.exception.code,code)
