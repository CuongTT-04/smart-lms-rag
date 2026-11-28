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

    def test_hint_retrieval_uses_public_text_exercise_and_stays_bounded(self):
        assessment = Assessment.objects.create(session=self.session, kind='TEXT', mode='PRACTICE',
            title='Vai trò ALU và CU', description='Nội dung đề công khai. ' * 500,
            hint='PRIVATE_TEACHER_HINT', due_at=timezone.now()+timedelta(days=1), is_published=True)
        self.data.update(mode='hint', question='Gợi ý cách đọc đề. ' * 400, assessment_id=str(assessment.pk))
        self.call()
        query = self.retrieval.call_args.args[1]
        self.assertIn(assessment.title, query)
        self.assertIn('Nội dung đề công khai.', query)
        self.assertLessEqual(len(query), 8000)
        self.assertNotIn('PRIVATE_TEACHER_HINT', query)

    def test_followups_are_optional_and_do_not_add_a_generation_call(self):
        self.hit['text'] = 'b) Đối tượng của triết học\nNguồn hiện tại.'
        result = self.call()
        self.assertTrue(2 <= len(result['suggested_questions']) <= 3)
        self.assertIn('Đối tượng của triết học', result['suggested_questions'][0])
        self.runtime.generate.assert_called_once()

    def test_tutoring_forwards_real_draft_with_only_public_exercise_fields(self):
        assessment = Assessment.objects.create(session=self.session, kind='TEXT', mode='PRACTICE',
            title='Vai trò ALU', description='Hãy nêu các nhóm phép toán.', hint='PRIVATE_TEACHER_HINT',
            due_at=timezone.now()+timedelta(days=1), is_published=True)
        self.data.update(mode='hint', question='Bản nháp: ALU chỉ cộng.', assessment_id=str(assessment.pk))
        tutoring = dict(action='practice', step=2, history=[])
        result = answer_chat(user=self.student, data=self.data, runtime=self.runtime,
            request_id=str(uuid4()), tutoring=tutoring)
        args = self.runtime.generate.call_args.kwargs
        self.assertEqual(args['question'], self.data['question'])
        self.assertEqual(args['tutoring'], tutoring)
        self.assertNotIn('PRIVATE_TEACHER_HINT', str(args))
        self.assertEqual(result['answer'], self.output['answer'])

    def test_followup_failure_preserves_answer_and_citations(self):
        with patch('apps.ai.followups.build_questions', side_effect=ValueError('private text')):
            with self.assertLogs('apps.ai.followups', level='WARNING'):
                result = self.call()
        self.assertEqual(result['answer'], 'Nội dung [1].')
        self.assertEqual(result['citations'][0]['excerpt'], 'Nguồn thật')
        self.assertEqual(result['suggested_questions'], [])

    def test_literal_cross_page_quote_keeps_its_source_context(self):
        self.version.page_count = 2
        self.version.save(update_fields=['page_count'])
        previous = 'Cách thứ nhất xử lý từng yêu cầu riêng biệt để giảm thời gian chờ.'
        transition = 'Bên cạnh cách thứ nhất, hệ thống còn xử lý theo'
        following = 'lô. Các yêu cầu được xử lý chung khi có đủ tài nguyên.'
        first = {**self.hit, 'text': previous + '\n' + transition}
        second = {**self.hit, 'chunk_id': 'chunk-2', 'text': following,
                  'source': {**self.hit['source'], 'page_number': 2}}
        self.retrieval.return_value = [first, second]
        self.runtime.generate.return_value = {**self.output,
            'answer': f'Trích học liệu:\n\n1. {transition} [1]\n2. {following} [2]',
            'references': [{'label': 1, 'source_id': 'S1'}, {'label': 2, 'source_id': 'S2'}]}
        result = self.call()
        self.assertIn(previous + ' [1]', result['answer'])
        self.assertIn(transition + ' [1] ' + following + ' [2]', result['answer'])
        self.assertEqual(result['citations'][0]['excerpt'], first['text'])
        self.assertEqual(result['citations'][1]['excerpt'], following)

    def test_indexing_not_ready_is_not_reported_as_academic_insufficiency(self):
        self.retrieval.side_effect = DocumentError('RETRIEVAL_NOT_READY', 'Chờ lập chỉ mục.', 503)
        with self.assertRaises(DocumentError) as caught:
            self.call()
        self.assertEqual(caught.exception.code, 'RETRIEVAL_NOT_READY')
        self.runtime.generate.assert_not_called()

    def test_incomplete_body_validation_is_preserved_without_procedure_fallback(self):
        self.runtime.generate.side_effect = DocumentError('GENERATION_INCOMPLETE_CONTENT', 'Thiếu nội dung.', 503)
        with self.assertRaises(DocumentError) as caught:
            self.call()
        self.assertEqual(caught.exception.code, 'GENERATION_INCOMPLETE_CONTENT')

    def test_history_retrieval_stays_within_query_limit_and_preserves_current_question(self):
        self.data['question'] = 'Q' * 8000
        history = [dict(question='Old topic', answer='Previous answer is not evidence')]
        self.runtime.generate.return_value = {**self.output, '_memory': dict(protocol='chat_history_v1')}
        answer_chat(user=self.student, data=self.data, runtime=self.runtime, request_id=str(uuid4()), history=history)
        query = self.retrieval.call_args.args[1]
        self.assertLessEqual(len(query), 8000)
        self.assertEqual(query, self.data['question'])
        self.assertEqual(self.runtime.generate.call_args.kwargs['history'], history)

    def test_independent_question_keeps_history_for_generation_but_not_retrieval(self):
        history=[dict(question='Chu kỳ xử lý lệnh CPU?',answer='Previous answer')]
        self.runtime.generate.return_value={**self.output,'_memory':dict(protocol='chat_history_v1')}
        for question in ['ALU là gì?','CPU gồm những thành phần nào?']:
            self.data['question']=question
            answer_chat(user=self.student,data=self.data,runtime=self.runtime,request_id=str(uuid4()),history=history)
            self.assertEqual(self.retrieval.call_args.args[1],question)
            self.assertEqual(self.runtime.generate.call_args.kwargs['history'],history)

    def test_explicit_followup_adds_previous_question_not_answer_to_retrieval(self):
        self.data['question']='Thành phần thứ hai có chức năng gì?'
        history=[dict(question='Các thành phần CPU?',answer='Previous answer')]
        self.runtime.generate.return_value={**self.output,'_memory':dict(protocol='chat_history_v1')}
        answer_chat(user=self.student,data=self.data,runtime=self.runtime,request_id=str(uuid4()),history=history)
        query=self.retrieval.call_args.args[1]
        self.assertIn(history[0]['question'],query)
        self.assertNotIn(history[0]['answer'],query)

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

    def test_incomplete_model_procedure_returns_cited_source_steps(self):
        self.version.page_count = 2
        self.version.save(update_fields=['page_count'])
        self.retrieval.return_value = [
            {**self.hit, 'text': 'Quy trình đăng ký (cont.)\nCác bước sau:\nChuẩn bị hồ sơ.\nGửi hồ sơ.\n<!-- image -->\nTên giảng viên'},
            {**self.hit, 'chunk_id': 'chunk-2', 'source': {**self.hit['source'], 'page_number': 2},
             'text': 'Quy trình đăng ký (cont.)\nNhận kết quả.\nVí dụ: Hồ sơ của lớp A.'},
        ]
        self.runtime.generate.side_effect = DocumentError('GENERATION_INCOMPLETE_ANSWER', 'Missing steps', 503)
        self.data['question'] = 'Quy trình đăng ký diễn ra như thế nào?'
        result = answer_chat(user=self.student, data=self.data, runtime=self.runtime, request_id=str(uuid4()), history=[])
        self.assertEqual(result['status'], 'ANSWERED')
        self.assertEqual([source['page_number'] for source in result['citations']], [1, 2])
        self.assertIn('1. Chuẩn bị hồ sơ. [1]', result['answer'])
        self.assertTrue(result['answer'].endswith('3. Nhận kết quả. [2]'))
        self.assertNotIn('Ví dụ', result['answer'])
        self.assertNotIn('Tên giảng viên', result['answer'])
        self.assertEqual(result['memory']['turns_used'], 0)
        from apps.ai.models import GenerationEvent
        event = GenerationEvent.objects.latest('created_at')
        self.assertEqual(event.code, 'GENERATION_INCOMPLETE_ANSWER')
        self.assertIsNotNone(event.recovered_at)
        self.data['question'] = 'Quy trình thanh toán diễn ra như thế nào?'
        with self.assertRaises(DocumentError) as caught:
            self.call()
        self.assertEqual(caught.exception.code, 'GENERATION_INCOMPLETE_ANSWER')

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
            assessment=Assessment.objects.create(session=self.session,title='Exam',kind='TEXT',mode='TEST',is_published=True,due_at=timezone.now()+timedelta(hours=1))
            AssessmentAttempt.objects.create(assessment=assessment,student=self.student,request_id=uuid4(),number=1,expires_at=assessment.due_at)
            return self.output
        self.runtime.generate.side_effect=generate
        with self.assertRaises(DocumentError) as caught: self.call()
        self.assertEqual(caught.exception.code,'AI_NOT_ALLOWED')

    def test_stateless_qa_enables_structured_citation_protocol_without_exposing_memory(self):
        self.runtime.generate.return_value = {
            **self.output,
            '_memory': dict(protocol='chat_history_v1', turns_used=0, turns_dropped=0, history_tokens=0),
        }
        result = self.call()
        self.assertEqual(self.runtime.generate.call_args.kwargs['history'], [])
        self.assertNotIn('memory', result)
        self.assertEqual(result['status'], 'ANSWERED')

        self.runtime.generate.return_value = {**self.output, '_memory': dict(protocol='legacy')}
        with self.assertRaises(DocumentError) as caught:
            self.call()
        self.assertEqual(caught.exception.code, 'GENERATION_CONFIG_MISMATCH')

        assessment = Assessment.objects.create(
            session=self.session, kind='TEXT', mode='PRACTICE',
            title='Ôn tập', description='Đọc tài liệu.', due_at=timezone.now() + timedelta(days=1),
            is_published=True,
        )
        self.data.update(mode='hint', assessment_id=str(assessment.pk))
        self.runtime.generate.return_value = self.output
        self.call()
        self.assertNotIn('history', self.runtime.generate.call_args.kwargs)

    def test_same_document_hits_within_budget_are_presented_in_page_reading_order(self):
        self.version.page_count = 3
        self.version.save(update_fields=['page_count'])
        p2 = {**self.hit, 'chunk_id': 'chunk-p2', 'text': 'Nội dung trang 2 về ALU.',
              'source': {**self.hit['source'], 'page_number': 2}}
        p1 = {**self.hit, 'chunk_id': 'chunk-p1', 'text': 'Nội dung trang 1 về CPU.',
              'source': {**self.hit['source'], 'page_number': 1}}
        p3 = {**self.hit, 'chunk_id': 'chunk-p3', 'text': 'Nội dung trang 3 về thanh ghi.',
              'source': {**self.hit['source'], 'page_number': 3}}
        self.retrieval.return_value = [p2, p1, p3]
        result = self.call()
        sent = self.runtime.generate.call_args.kwargs['contexts']
        self.assertEqual([c['page_number'] for c in sent], [1, 2, 3])
        self.assertEqual([c['source_id'] for c in sent], ['S1', 'S2', 'S3'])
        self.assertEqual(result['citations'][0]['page_number'], 1)
        self.assertEqual(result['citations'][0]['excerpt'], p1['text'])

        # Oversized context sets keep retrieval rank order so token budgeting does not drop top hits.
        large_p2 = {**p2, 'text': 'A' * 1600}
        large_p1 = {**p1, 'text': 'B' * 1600}
        self.retrieval.return_value = [large_p2, large_p1]
        self.call()
        sent_large = self.runtime.generate.call_args.kwargs['contexts']
        self.assertEqual([c['page_number'] for c in sent_large], [2, 1])
