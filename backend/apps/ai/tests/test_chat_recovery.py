from unittest import TestCase
from unittest.mock import patch
from apps.ai.providers import GenerationError
from apps.ai.rag import RAGPipeline
from apps.ai.tests import test_rag_pipeline as fixtures


class SequenceProvider(fixtures.FakeProvider):
    def __init__(self, texts):
        super().__init__(); self.texts=iter(texts); self.requests=[]; self.deadlines=[]
    def generate(self, messages, *, timeout_seconds=None):
        self.requests.append(messages); self.deadlines.append(timeout_seconds)
        self.generate_calls+=1; self.text=next(self.texts)
        return self.result(messages)


class ChatRecoveryTests(TestCase):
    def setUp(self):
        fixture=fixtures.RAGPipelineTests(); fixture.setUp(); self.context=fixture.first
    def run_chat(self, provider, **extra):
        return RAGPipeline(provider).generate_answer(question='CPU?',mode='qa',contexts=[self.context],history=[],**extra)
    def test_missing_citation_and_mixed_output_regenerate_once(self):
        for bad in ['CU va ALU.', 'CU. INSUFFICIENT_EVIDENCE']:
            with self.subTest(bad=bad):
                provider=SequenceProvider([bad,'Noi dung [1].'])
                result=self.run_chat(provider)
                self.assertEqual(result.status,'ANSWERED')
                self.assertEqual(provider.generate_calls,2)
                self.assertNotEqual(provider.requests[0][0]['content'],provider.requests[1][0]['content'])
                self.assertNotIn(bad,provider.requests[1][-1]['content'])
                self.assertGreater(provider.deadlines[1],0)
                self.assertLessEqual(provider.deadlines[1],provider.config.timeout_seconds)
    def test_structured_retry_renders_only_model_assigned_inline_sources(self):
        from dataclasses import replace
        import json
        provider=SequenceProvider(['Nội dung thiếu citation.',json.dumps({'items':[{'text':'Ý thứ nhất.','sources':[2]},{'text':'Ý thứ hai.','sources':[1,2]}]},ensure_ascii=False)])
        second=replace(self.context,source_id='S2',chunk_id='b',text='Nguồn thứ hai')
        result=RAGPipeline(provider).generate_answer(question='CPU?',mode='qa',contexts=[self.context,second],history=[])
        self.assertEqual(result.answer,'1. Ý thứ nhất. [1]\n2. Ý thứ hai. [2] [1]')
        self.assertEqual([r.source_id for r in result.references],['S2','S1'])
        self.assertEqual(provider.generate_calls,2)
    def test_structured_retry_refuses_unknown_sources_or_unbound_items(self):
        import json
        for item in [{'text':'Claim','sources':[]},{'text':'Claim','sources':[99]},{'text':'Claim','sources':[True]},{'text':'Claim [1]','sources':[1]},{'text':'Claim','sources':[1],'extra':'secret'}]:
            with self.subTest(item=item):
                provider=SequenceProvider(['Claim without citation',json.dumps({'items':[item]})])
                with self.assertRaises(GenerationError):self.run_chat(provider)
                self.assertEqual(provider.generate_calls,2)

    def test_reported_cpu_shape_has_seven_explicit_sources_after_intro(self):
        import json
        items=[{'text':'Mỗi chu kỳ xử lý lệnh CPU bao gồm các bước sau:'}]+[{'text':str(i)+'. Bước minh họa '+str(i)+'.'} for i in range(1,8)]
        raw=json.dumps({'items':items,'sources':[1]*7},ensure_ascii=False)
        provider=SequenceProvider(['Nội dung thiếu citation.',raw]);result=self.run_chat(provider)
        self.assertEqual(result.answer,'\n'.join(str(i)+'. Bước minh họa '+str(i)+'. [1]' for i in range(1,8)))
        self.assertEqual(provider.generate_calls,2)
    def test_parallel_sources_preserve_per_item_model_assignments(self):
        import json
        from dataclasses import replace
        raw=json.dumps({'items':[{'text':'Ý A.'},{'text':'Ý B.'}],'sources':[[2],[1,2]]},ensure_ascii=False)
        provider=SequenceProvider(['Missing source',raw])
        second=replace(self.context,source_id='S2',chunk_id='b',text='Second source')
        result=RAGPipeline(provider).generate_answer(question='CPU?',mode='qa',contexts=[self.context,second],history=[])
        self.assertEqual(result.answer,'1. Ý A. [1]\n2. Ý B. [2] [1]')
        self.assertEqual([r.source_id for r in result.references],['S2','S1'])
    def test_parallel_sources_do_not_broadcast_or_drop_an_unbound_claim(self):
        import json
        cases=[
            {'items':[{'text':'A.'},{'text':'B.'}],'sources':[1]},
            {'items':[{'text':'An unsupported factual claim.'},{'text':'A.'},{'text':'B.'}],'sources':[1,1]},
            {'items':[{'text':'A.'}],'sources':[True]},
            {'items':[{'text':'A.'}],'sources':[99]},
            {'items':[{'text':'A.','sources':[1]}],'sources':[1]},
        ]
        for value in cases:
            with self.subTest(value=value):
                provider=SequenceProvider(['Missing citation',json.dumps(value)])
                with self.assertRaises(GenerationError):self.run_chat(provider)

    def test_structured_retry_requests_a_schema_when_provider_supports_it(self):
        class Constrained(SequenceProvider):
            def generate(inner,messages,*,timeout_seconds=None,json_schema=None):
                inner.last_schema=json_schema
                return super(Constrained,inner).generate(messages,timeout_seconds=timeout_seconds)
        provider=Constrained(['Missing citation','{"items":[]}'])
        result=self.run_chat(provider)
        self.assertEqual(result.status,'INSUFFICIENT_EVIDENCE')
        self.assertEqual(provider.last_schema['properties']['items']['items']['properties']['evidence_id']['enum'],['E1.1'])
        self.assertEqual(provider.last_schema['properties']['items']['minItems'],0)

    def test_bibliography_footer_is_regenerated_with_inline_citations(self):
        bad='ALU co hai cong vao.\n\nCitation:\n[1] Ten tac gia, trang 23.'
        provider=SequenceProvider([bad,'ALU co hai cong vao [1].'])
        result=self.run_chat(provider)
        self.assertEqual(result.answer,'ALU co hai cong vao [1].')
        self.assertEqual(provider.generate_calls,2)
    def test_uncited_list_items_cannot_be_covered_by_a_final_label(self):
        bad='1. Cong vao.\n2. Cong ra.\n\n[1]'
        provider=SequenceProvider([bad,bad])
        with self.assertRaises(GenerationError):self.run_chat(provider)
        self.assertEqual(provider.generate_calls,2)
    def test_each_list_item_needs_its_own_citation(self):
        bad='1. Cong vao.\n2. Cong ra [1].'
        provider=SequenceProvider([bad,'1. Cong vao [1].\n2. Cong ra [1].'])
        result=self.run_chat(provider)
        self.assertEqual(provider.generate_calls,2)
        self.assertEqual(result.answer.count('[1]'),2)
    def test_inline_citations_in_wrapped_list_and_paragraph_pass_without_retry(self):
        text='ALU:\n1. Hai cong vao\nnhan toan hang [1].\n2. Cong ra [1].\n\nThuc hien phep tinh [1].'
        provider=SequenceProvider([text]);result=self.run_chat(provider)
        self.assertEqual(provider.generate_calls,1)
        self.assertEqual(result.answer,text)

    def test_second_invalid_answer_still_fails_without_inventing_citations(self):
        provider=SequenceProvider(['CU.','CU again.'])
        with self.assertRaises(GenerationError) as caught:self.run_chat(provider)
        self.assertEqual(caught.exception.validation_reason,'MISSING_CITATION')
        self.assertEqual(provider.generate_calls,2)
    def test_unknown_source_is_not_repaired(self):
        provider=SequenceProvider(['Noi dung [999].'])
        with self.assertRaises(GenerationError):self.run_chat(provider)
        self.assertEqual(provider.generate_calls,1)
    def test_valid_answer_or_insufficient_evidence_is_not_retried(self):
        for text in ['Noi dung [1].','INSUFFICIENT_EVIDENCE']:
            provider=SequenceProvider([text]); self.run_chat(provider)
            self.assertEqual(provider.generate_calls,1)
    def test_provider_without_retry_deadline_support_fails_closed(self):
        provider=fixtures.FakeProvider(); provider.text='CU.'
        with self.assertRaises(GenerationError):self.run_chat(provider)
        self.assertEqual(provider.generate_calls,1)
    def test_stateless_baseline_does_not_retry(self):
        provider=SequenceProvider(['CU.'])
        with self.assertRaises(GenerationError):
            RAGPipeline(provider).generate_answer(question='CPU?',mode='qa',contexts=[self.context])
        self.assertEqual(provider.generate_calls,1)
    def test_expired_request_does_not_start_second_attempt(self):
        provider=SequenceProvider(['CU.'])
        with patch('apps.ai.rag.pipeline.perf_counter',side_effect=[0,0,100]):
            with self.assertRaises(GenerationError):self.run_chat(provider)
        self.assertEqual(provider.generate_calls,1)


class RetrievalQuestionTests(TestCase):
    def query(self,question,history):
        from apps.ai.rag.conversation import retrieval_query
        return retrieval_query(question,history)
    def test_standalone_questions_do_not_inherit_previous_topic(self):
        history=[dict(question='Chu ky lenh CPU?',answer='Old answer')]
        for q in ['CPU gồm những thành phần nào?','ALU là gì?']:
            self.assertEqual(self.query(q,history),q)
    def test_explicit_followups_use_only_previous_question(self):
        history=[dict(question='Các thành phần CPU?',answer='Untrusted previous answer')]
        for q in ['Thành phần thứ hai có chức năng gì?','Nó hoạt động thế nào?','Giải thích ý vừa nêu']:
            query=self.query(q,history)
            self.assertIn(history[-1]['question'],query)
            self.assertNotIn(history[-1]['answer'],query)
            self.assertTrue(query.startswith(q))
    def test_query_is_bounded(self):
        question='Nó '+('Q'*7997)
        self.assertEqual(self.query(question,[dict(question='Old',answer='Old')]),question)


class ClaimEvidenceTests(TestCase):
    def setUp(self):
        fixture=fixtures.RAGPipelineTests();fixture.setUp();self.context=fixture.first
    def render(self,value):
        import json
        from apps.ai.rag.conversation import render_structured_answer
        return render_structured_answer(json.dumps(value,ensure_ascii=False),[self.context],require_proof=True)
    def test_one_verified_source_is_rendered_for_each_atomic_claim(self):
        result=self.render({'items':[{'text':'Một ý.','source':1,'quote':self.context.text}]})
        self.assertEqual(result,'Một ý. [1]')
    def test_fake_quote_unknown_source_and_blanket_arrays_are_rejected(self):
        for item in [dict(text='Ý.',source=1,quote='A fabricated quotation that is not present.'),
                     dict(text='Ý.',source=99,quote=self.context.text),
                     dict(text='Ý.',sources=[1,2,3],quote=self.context.text),
                     dict(text='Ý.',source=1,quote='tài liệu')]:
            with self.subTest(item=item),self.assertRaises(GenerationError):self.render({'items':[item]})
    def test_whitespace_only_pdf_wrapping_can_be_normalized_for_quote_matching(self):
        self.context=__import__('dataclasses').replace(self.context,text='ALU có hai cổng IN\nđể nhận đầu vào từ các thanh ghi.')
        self.assertEqual(self.render({'items':[dict(text='ALU nhận đầu vào.',source=1,quote='hai cổng IN để nhận đầu vào từ các thanh ghi.')] }),'ALU nhận đầu vào. [1]')
    def test_quote_from_another_chunk_cannot_be_used_for_the_selected_source(self):
        import json
        from dataclasses import replace
        from apps.ai.rag.conversation import render_structured_answer
        other=replace(self.context,source_id='S2',chunk_id='other',text='Một đoạn khác chỉ mô tả hoạt động điều khiển.')
        raw=json.dumps({'items':[dict(text='Claim',source=2,quote=self.context.text)]})
        with self.assertRaises(GenerationError):render_structured_answer(raw,[self.context,other],require_proof=True)

    def test_constrained_chat_starts_with_proof_and_isolates_unrelated_history(self):
        import json
        context=self.context
        class Constrained(SequenceProvider):
            def generate(inner,messages,*,timeout_seconds=None,json_schema=None):
                inner.schema=json_schema
                return super(Constrained,inner).generate(messages,timeout_seconds=timeout_seconds)
        provider=Constrained([json.dumps({'items':[dict(text='Ý mới.',evidence_id='E1.1')]},ensure_ascii=False)])
        result=RAGPipeline(provider).generate_answer(question='ALU là gì?',mode='qa',contexts=[context],history=[dict(question='Chu kỳ CPU?',answer='Old PC MAR IR answer')])
        self.assertEqual(provider.generate_calls,1)
        self.assertEqual([m['role'] for m in provider.requests[0]],['system','user'])
        self.assertEqual(set(provider.schema['properties']['items']['items']['required']),{'text','evidence_id'})
        self.assertEqual(result.trace.memory['turns_used'],0)
        self.assertEqual(result.answer,'Ý mới. [1]')

    def test_standalone_alu_does_not_include_old_cpu_answers_in_prompt(self):
        from apps.ai.rag.conversation import prepare_conversation_prompt
        from apps.ai.rag import GenerationConfig
        provider=fixtures.FakeProvider()
        prepared,memory=prepare_conversation_prompt(question='ALU là gì?',mode='qa',contexts=[self.context],exercise=None,
            config=GenerationConfig(model=provider.config),provider=provider,history=[dict(question='Các bước CPU?',answer='PC MAR IR CU')])
        self.assertEqual([m['role'] for m in prepared.messages],['system','user'])
        self.assertEqual(memory['turns_used'],0)
        self.assertEqual(memory['turns_dropped'],1)


class EvidenceIdCitationTests(TestCase):
    def setUp(self):
        from dataclasses import replace
        fixture=fixtures.RAGPipelineTests(); fixture.setUp()
        self.first=replace(fixture.first,text='Chu kỳ xử lý lệnh CPU\nMMU chọn ô nhớ và sinh tín hiệu READ.')
        self.second=replace(self.first,source_id='S2',chunk_id='second',text='ALU thực hiện phép toán số học và logic.')

    def test_evidence_units_bind_exact_text_to_current_source(self):
        from apps.ai.rag.conversation import build_evidence_units
        units=build_evidence_units([self.first,self.second])
        self.assertEqual([(u['evidence_id'],u['citation_label']) for u in units],[('E1.1',1),('E1.2',1),('E2.1',2)])
        self.assertEqual(units[1]['text'],'MMU chọn ô nhớ và sinh tín hiệu READ.')
        self.assertEqual(build_evidence_units([self.first,self.second]),units)

    def test_schema_only_allows_explicit_available_evidence_ids(self):
        from apps.ai.rag.conversation import citation_response_schema
        schema=citation_response_schema(2,evidence_ids=['E1.1','E1.2','E2.1'])
        item=schema['properties']['items']['items']
        self.assertEqual(set(item['required']),{'text','evidence_id'})
        self.assertEqual(item['properties']['evidence_id']['enum'],['E1.1','E1.2','E2.1'])
        self.assertFalse(item['additionalProperties'])

    def test_render_uses_model_selected_id_without_broadcasting_sources(self):
        import json
        from apps.ai.rag.conversation import render_structured_answer
        raw=json.dumps({'items':[{'text':'ALU thực hiện phép toán.','evidence_id':'E2.1'},
                                 {'text':'MMU chọn ô nhớ.','evidence_id':'E1.2'}]},ensure_ascii=False)
        rendered=render_structured_answer(raw,[self.first,self.second],require_proof=True)
        self.assertEqual(rendered,'1. ALU thực hiện phép toán. [2]\n2. MMU chọn ô nhớ. [1]')
        from apps.ai.rag.citations import parse_answer
        _,answer,refs,_=parse_answer(rendered,[self.first,self.second])
        self.assertEqual([ref.source_id for ref in refs],['S2','S1'])
        self.assertEqual(answer,'1. ALU thực hiện phép toán. [1]\n2. MMU chọn ô nhớ. [2]')

    def test_unknown_missing_or_foreign_evidence_id_fails_closed(self):
        import json
        from apps.ai.rag.conversation import render_structured_answer
        for item in [dict(text='Claim',evidence_id='E9.1'),dict(text='Claim',evidence_id='E1.99'),
                     dict(text='Claim'),dict(text='Claim',evidence_id=['E1.1','E2.1']),
                     dict(text='Claim',evidence_id='E1.1',quote='Invented')]:
            with self.subTest(item=item),self.assertRaises(GenerationError):
                render_structured_answer(json.dumps({'items':[item]}),[self.first],require_proof=True)

    def test_prompt_exposes_only_server_assigned_ids_and_exact_excerpts(self):
        import json
        from apps.ai.rag.conversation import prepare_conversation_prompt
        from apps.ai.rag import GenerationConfig
        provider=fixtures.FakeProvider()
        prepared,_=prepare_conversation_prompt(question='CPU?',mode='qa',contexts=[self.first,self.second],exercise=None,
            config=GenerationConfig(model=provider.config),provider=provider,history=[],repair_format=True)
        evidence=json.loads(prepared.messages[-1]['content'])['evidence']
        self.assertEqual([u['evidence_id'] for u in evidence],['E1.1','E1.2','E2.1'])
        self.assertIn('evidence_citations_v2',prepared.messages[0]['content'])

    def test_legacy_quote_mismatch_has_its_own_error_reason(self):
        import json
        from apps.ai.rag.conversation import render_structured_answer
        with self.assertRaises(GenerationError) as caught:
            render_structured_answer(json.dumps({'items':[dict(text='Claim',source=1,quote='An invented source quotation here')]}),[self.first],require_proof=True)
        self.assertEqual(caught.exception.validation_reason,'EVIDENCE_QUOTE_MISMATCH')


class ProcedureCompletenessTests(TestCase):
    def setUp(self):
        import json
        from dataclasses import replace
        fixture=fixtures.RAGPipelineTests();fixture.setUp()
        self.context=replace(fixture.first,text='Quy trình đăng ký\nThực hiện theo các bước sau:\nChuẩn bị hồ sơ.\nGửi hồ sơ.\nNhận kết quả.')
        self.question='Quy trình đăng ký diễn ra như thế nào?'
        self.bad=json.dumps({'items':[dict(text='Thực hiện theo các bước sau:',evidence_id='E1.2'),
            dict(text='- Gửi hồ sơ.',evidence_id='E1.4'),dict(text='- Nhận kết quả.',evidence_id='E1.5')]},ensure_ascii=False)
        self.good=json.dumps({'items':[dict(text='Chuẩn bị hồ sơ.',evidence_id='E1.3'),
            dict(text='Gửi hồ sơ.',evidence_id='E1.4'),dict(text='Nhận kết quả.',evidence_id='E1.5')]},ensure_ascii=False)

    def provider(self,texts):
        class Constrained(SequenceProvider):
            def generate(inner,messages,*,timeout_seconds=None,json_schema=None):
                return super(Constrained,inner).generate(messages,timeout_seconds=timeout_seconds)
        return Constrained(texts)

    def test_render_removes_nonfactual_intro_and_repeated_list_markers(self):
        from apps.ai.rag.conversation import render_structured_answer
        self.assertEqual(render_structured_answer(self.bad,[self.context],require_proof=True),
                         '1. Gửi hồ sơ. [1]\n2. Nhận kết quả. [1]')

    def test_missing_first_step_gets_one_bounded_retry_with_current_evidence(self):
        import json
        provider=self.provider([self.bad,self.good])
        result=RAGPipeline(provider).generate_answer(question=self.question,mode='qa',contexts=[self.context],history=[])
        self.assertEqual(provider.generate_calls,2)
        self.assertEqual(result.answer,'1. Chuẩn bị hồ sơ. [1]\n2. Gửi hồ sơ. [1]\n3. Nhận kết quả. [1]')
        feedback=json.loads(provider.requests[1][-1]['content'])['repair_feedback']
        self.assertEqual(feedback['required_evidence_ids'],['E1.3'])
        self.assertNotIn('Gửi hồ sơ.',feedback['instruction'])
        self.assertGreater(provider.deadlines[1],0)

    def test_second_missing_first_step_fails_without_inserting_text(self):
        provider=self.provider([self.bad,self.bad])
        with self.assertRaises(GenerationError) as caught:
            RAGPipeline(provider).generate_answer(question=self.question,mode='qa',contexts=[self.context],history=[])
        self.assertEqual(caught.exception.validation_reason,'INCOMPLETE_EVIDENCE_COVERAGE')
        self.assertEqual(provider.generate_calls,2)

    def test_narrow_question_does_not_require_unasked_preparation(self):
        import json
        provider=self.provider([json.dumps({'items':[dict(text='Gửi hồ sơ.',evidence_id='E1.4')]})])
        result=RAGPipeline(provider).generate_answer(question='Bước gửi hồ sơ là gì?',mode='qa',contexts=[self.context],history=[])
        self.assertEqual(result.answer,'Gửi hồ sơ. [1]')
        self.assertEqual(provider.generate_calls,1)

    def test_feedback_is_bound_to_source_and_excerpt_when_labels_change(self):
        import json
        from dataclasses import replace
        from apps.ai.rag import GenerationConfig
        from apps.ai.rag.conversation import prepare_conversation_prompt
        provider=fixtures.FakeProvider()
        other=replace(self.context,source_id='S2',chunk_id='unrelated',text='Nguồn khác.')
        prepared,_=prepare_conversation_prompt(question=self.question,mode='qa',contexts=[other,self.context],exercise=None,
            config=GenerationConfig(model=provider.config),provider=provider,history=[],repair_format=True,
            repair_feedback=[{'source_id':self.context.source_id,'text':'Chuẩn bị hồ sơ.'}])
        self.assertEqual(json.loads(prepared.messages[-1]['content'])['repair_feedback']['required_evidence_ids'],['E2.3'])
