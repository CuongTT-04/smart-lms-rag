"""Small deterministic guards; semantic citation review still needs source inspection."""
import json
from dataclasses import replace
from unittest import TestCase

from apps.ai.providers import GenerationError
from apps.ai.rag import RAGPipeline
from apps.ai.rag.conversation import (build_evidence_units, render_structured_answer,
                                      description_evidence_groups, validate_copied_claim_sources,
                                      render_source_selection, source_selection_schema,
                                      validate_description_coverage, validate_answer_body,
                                      validate_enumeration_coverage)
from apps.ai.rag.conversation import multipart_evidence_groups, validate_multipart_coverage
from apps.ai.rag.errors import public_validation_error
from apps.ai.tests.test_chat_recovery import SequenceProvider
from apps.ai.tests import test_rag_pipeline as fixtures


class AnswerCompletenessTests(TestCase):
    def setUp(self):
        fixture = fixtures.RAGPipelineTests()
        fixture.setUp()
        self.context = replace(fixture.first, text=(
            'Triết học chỉ xuất hiện trong những điều kiện nhất định sau đây:\n'
            'Con người có vốn hiểu biết và khả năng khái quát.\n'
            'Xã hội hình thành tầng lớp lao động trí óc.'))

    def run_chat(self, provider):
        return RAGPipeline(provider).generate_answer(
            question='Triết học ra đời trong những điều kiện nào?', mode='qa',
            contexts=[self.context], history=[])

    def test_bare_introduction_is_rejected(self):
        with self.assertRaises(GenerationError) as caught:
            validate_answer_body('Triết học xuất hiện trong những điều kiện sau đây: [1]')
        self.assertEqual(caught.exception.validation_reason, 'INCOMPLETE_ANSWER_BODY')

    def test_multiple_introductions_are_not_substantive(self):
        with self.assertRaises(GenerationError):
            validate_answer_body('1. Các điều kiện sau: [1]\n2. Cụ thể như sau: [1]')

    def test_page_boundary_dangling_clause_is_rejected(self):
        with self.assertRaises(GenerationError) as caught:
            validate_answer_body('Đây là thời kỳ cơ học thu được những thành tựu rực rỡ nên trong [1]')
        self.assertEqual(caught.exception.validation_reason, 'INCOMPLETE_ANSWER_BODY')

    def test_complete_clause_after_page_continuation_is_allowed(self):
        validate_answer_body('Tư duy máy móc xem mỗi bộ phận ở trạng thái biệt lập và tĩnh tại. [1]')

    def test_quoted_conjunction_is_not_mistaken_for_a_dangling_clause(self):
        validate_answer_body('Một ví dụ về liên từ tiếng Việt là "và". [1]')

    def test_real_answer_and_introduction_with_body_are_allowed(self):
        for answer in ['Con người có vốn hiểu biết và khả năng khái quát. [1]',
                       'Các điều kiện sau:\nCon người có vốn hiểu biết. [1]',
                       'Triết học có nguồn gốc nhận thức và nguồn gốc xã hội. [1]']:
            with self.subTest(answer=answer):
                validate_answer_body(answer)

    def test_single_structured_intro_cannot_be_answered(self):
        raw = json.dumps({'items': [dict(text='Các điều kiện sau đây:', evidence_id='E1.1')]})
        with self.assertRaises(GenerationError) as caught:
            render_structured_answer(raw, [self.context], require_proof=True)
        self.assertEqual(caught.exception.validation_reason, 'INCOMPLETE_ANSWER_BODY')

    def test_intro_is_removed_when_real_items_follow(self):
        raw = json.dumps({'items': [
            dict(text='Các điều kiện sau đây:', evidence_id='E1.1'),
            dict(text='Con người có vốn hiểu biết.', evidence_id='E1.2')]})
        self.assertEqual(render_structured_answer(raw, [self.context], require_proof=True),
                         'Con người có vốn hiểu biết. [1]')

    def test_chat_retries_once_and_keeps_source_assignment(self):
        provider = SequenceProvider(['Các điều kiện sau đây: [1]',
                                     'Con người có vốn hiểu biết và khả năng khái quát. [1]'])
        result = self.run_chat(provider)
        self.assertEqual(result.status, 'ANSWERED')
        self.assertEqual(provider.generate_calls, 2)
        self.assertGreater(provider.deadlines[1], 0)
        self.assertLessEqual(provider.deadlines[1], provider.config.timeout_seconds)

    def test_second_intro_fails_without_source_fabrication(self):
        provider = SequenceProvider(['Các điều kiện sau đây: [1]'] * 2)
        with self.assertRaises(GenerationError) as caught:
            self.run_chat(provider)
        self.assertEqual(provider.generate_calls, 2)
        self.assertEqual(caught.exception.validation_reason, 'INCOMPLETE_ANSWER_BODY')

    def test_empty_structured_items_still_mean_insufficient_evidence(self):
        self.assertEqual(render_structured_answer('{"items":[]}', [self.context], require_proof=True),
                         'INSUFFICIENT_EVIDENCE')

    def test_absence_only_claims_are_not_published_as_grounded_answers(self):
        raw = json.dumps(dict(items=[dict(text='Không có thông tin về vấn đề này.', evidence_id='E1.1'),
                                     dict(text='Chủ đề này không được đề cập.', evidence_id='E1.2')]))
        self.assertEqual(render_structured_answer(raw, [self.context], require_proof=True),
                         'INSUFFICIENT_EVIDENCE')

    def test_explicit_negative_fact_in_source_is_not_automatically_a_refusal(self):
        context = replace(self.context, text='Phụ lục ghi rõ: Không có thông tin về tác giả trong hồ sơ.')
        raw = json.dumps(dict(items=[dict(text='Không có thông tin về tác giả trong hồ sơ.', evidence_id='E1.1')]))
        self.assertIn('[1]', render_structured_answer(raw, [context], require_proof=True))

    def test_absence_notice_does_not_acquire_citations_in_pipeline(self):
        class Constrained(SequenceProvider):
            def generate(inner, messages, *, timeout_seconds=None, json_schema=None):
                return super().generate(messages, timeout_seconds=timeout_seconds)
        provider = Constrained([json.dumps(dict(items=[dict(text='Không có thông tin về chủ đề này.',
                                                            evidence_id='E1.1')]))])
        result = self.run_chat(provider)
        self.assertEqual(result.status, 'INSUFFICIENT_EVIDENCE')
        self.assertEqual(result.references, ())

    def test_mixed_grounded_answer_and_unsupported_absence_is_not_silently_trimmed(self):
        raw = json.dumps(dict(items=[dict(text='Con người có vốn hiểu biết.', evidence_id='E1.2'),
                                     dict(text='Không có thông tin về chủ đề khác.', evidence_id='E1.1')]))
        with self.assertRaises(GenerationError):
            render_structured_answer(raw, [self.context], require_proof=True)

    def test_structured_retry_gets_actionable_feedback_not_identical_prompt(self):
        class Constrained(SequenceProvider):
            def generate(inner, messages, *, timeout_seconds=None, json_schema=None):
                return super().generate(messages, timeout_seconds=timeout_seconds)
        provider = Constrained([
            json.dumps({'items': [dict(text='Các điều kiện sau đây:', evidence_id='E1.1')]}),
            json.dumps({'items': [dict(text='Con người có vốn hiểu biết.', evidence_id='E1.2')]})])
        result = self.run_chat(provider)
        self.assertEqual(result.status, 'ANSWERED')
        self.assertEqual(provider.generate_calls, 2)
        first = json.loads(provider.requests[0][-1]['content'])
        second = json.loads(provider.requests[1][-1]['content'])
        self.assertNotIn('repair_feedback', first)
        self.assertEqual(second['repair_feedback']['validation_reason'], 'INCOMPLETE_ANSWER_BODY')
        self.assertNotEqual(first, second)
        self.assertNotIn('required_evidence_ids', second['repair_feedback'])
        self.assertEqual(first['evidence'], second['evidence'])

    def test_stateless_baseline_is_not_changed(self):
        provider = SequenceProvider(['Các điều kiện sau đây: [1]'])
        result = RAGPipeline(provider).generate_answer(question='Điều kiện nào?', mode='qa',
                                                       contexts=[self.context])
        self.assertEqual(result.status, 'ANSWERED')
        self.assertEqual(provider.generate_calls, 1)

    def test_public_failure_has_specific_safe_message(self):
        code, message, status = public_validation_error('INCOMPLETE_ANSWER_BODY')
        self.assertEqual((code, status), ('GENERATION_INCOMPLETE_CONTENT', 503))
        self.assertIn('câu dẫn', message)


class MultipartCoverageTests(TestCase):
    def setUp(self):
        fixture = fixtures.RAGPipelineTests()
        fixture.setUp()
        self.contexts = [replace(fixture.first, text='Chu kỳ lệnh gồm nạp, giải mã và thực thi.'),
                         replace(fixture.second, text='Các phép toán logic gồm AND, OR, XOR, NOT.')]
        self.question = 'Nêu chu kỳ lệnh và các phép toán logic, trích nguồn cho từng ý.'

    def test_missing_requested_topic_is_repaired_with_its_actual_source(self):
        class Constrained(SequenceProvider):
            def generate(inner, messages, *, timeout_seconds=None, json_schema=None):
                return super().generate(messages, timeout_seconds=timeout_seconds)
        first = dict(text='Các phép toán logic gồm AND, OR, XOR, NOT.', evidence_id='E2.1')
        second = dict(text='Chu kỳ lệnh gồm nạp, giải mã và thực thi.', evidence_id='E1.1')
        provider = Constrained([json.dumps(dict(items=[first])), json.dumps(dict(items=[second, first]))])
        result = RAGPipeline(provider).generate_answer(question=self.question, mode='qa',
                                                     contexts=self.contexts, history=[])
        self.assertEqual(provider.generate_calls, 2)
        self.assertIn('Chu kỳ lệnh', result.answer)
        first_prompt = json.loads(provider.requests[0][-1]['content'])
        self.assertEqual(len(first_prompt['question_parts']), 2)
        repaired = json.loads(provider.requests[1][-1]['content'])
        self.assertEqual(repaired['repair_feedback']['required_evidence_ids'], ['E1.1'])

    def test_empty_answer_single_topic_and_ambiguous_shared_evidence_are_not_forced(self):
        validate_multipart_coverage(self.question, '{"items":[]}', self.contexts)
        self.assertEqual(multipart_evidence_groups('Chu kỳ lệnh là gì?', self.contexts), [])
        shared = [replace(self.contexts[0], text='Chu kỳ lệnh và các phép toán logic cùng được mô tả ở đây.')]
        self.assertEqual(multipart_evidence_groups(self.question, shared), [])

    def test_unrelated_extra_source_is_not_required(self):
        contexts = [*self.contexts, replace(self.contexts[0], source_id='S99', text='Tài liệu khác không liên quan.')]
        raw = json.dumps(dict(items=[dict(text='Ý một.', evidence_id='E1.1'),
                                     dict(text='Ý hai.', evidence_id='E2.1')]))
        validate_multipart_coverage(self.question, raw, contexts)

    def test_accented_question_matches_unaccented_source_without_changing_source_text(self):
        contexts = [replace(self.contexts[0], text='Chu ky lenh gom nap, giai ma va thuc thi.'),
                    replace(self.contexts[1], text='Cac phep toan logic gom AND, OR, XOR, NOT.')]
        raw = json.dumps(dict(items=[dict(text='Các phép toán logic gồm AND, OR, XOR, NOT.',
                                         evidence_id='E2.1')]))
        with self.assertRaises(GenerationError) as caught:
            validate_multipart_coverage(self.question, raw, contexts)
        self.assertEqual(caught.exception.missing_evidence[0]['text'], contexts[0].text)


class EnumerationCoverageTests(TestCase):
    def setUp(self):
        fixture = fixtures.RAGPipelineTests()
        fixture.setUp()
        self.context = replace(fixture.first, text=(
            'Vấn đề cơ bản của triết học có hai mặt.\n'
            'Mặt thứ nhất: Quan hệ giữa vật chất và ý thức.\n'
            'Mặt thứ hai: Khả năng nhận thức thế giới.'))
        self.question = 'Vấn đề cơ bản của triết học có hai mặt nào?'

    def validate(self, ids, question=None):
        raw = json.dumps({'items': [dict(text='Một ý.', evidence_id=value) for value in ids]})
        validate_enumeration_coverage(question or self.question, raw, [self.context])

    def test_count_only_answer_is_rejected_with_required_source_lines(self):
        with self.assertRaises(GenerationError) as caught:
            self.validate(['E1.1'])
        self.assertEqual(caught.exception.validation_reason, 'INCOMPLETE_ENUMERATION')
        self.assertEqual(len(caught.exception.missing_evidence), 2)

    def test_missing_second_side_is_rejected(self):
        with self.assertRaises(GenerationError):
            self.validate(['E1.2'])

    def test_both_explicit_sides_are_accepted(self):
        self.validate(['E1.2', 'E1.3'])

    def test_count_or_narrow_question_does_not_force_unasked_items(self):
        for question in ['Vấn đề cơ bản có mấy mặt?', 'Mặt thứ nhất nói về điều gì?']:
            self.validate(['E1.1'], question)

    def test_empty_items_can_refuse_without_forced_evidence(self):
        self.validate([])

    def test_enumeration_retry_receives_only_current_required_evidence(self):
        class Constrained(SequenceProvider):
            def generate(inner, messages, *, timeout_seconds=None, json_schema=None):
                return super().generate(messages, timeout_seconds=timeout_seconds)
        provider = Constrained([
            json.dumps({'items': [dict(text='Có hai mặt.', evidence_id='E1.1')]}),
            json.dumps({'items': [dict(text='Quan hệ vật chất và ý thức.', evidence_id='E1.2'),
                                 dict(text='Khả năng nhận thức thế giới.', evidence_id='E1.3')]})])
        result = RAGPipeline(provider).generate_answer(question=self.question, mode='qa', contexts=[self.context], history=[])
        self.assertEqual(provider.generate_calls, 2)
        self.assertEqual(result.status, 'ANSWERED')
        feedback = json.loads(provider.requests[1][-1]['content'])['repair_feedback']
        self.assertEqual(feedback['required_evidence_ids'], ['E1.2', 'E1.3'])


class AtomicEvidenceTests(TestCase):
    def setUp(self):
        fixture = fixtures.RAGPipelineTests()
        fixture.setUp()
        self.context = fixture.first
        self.long = ('Một câu mô tả quan điểm được học liệu nêu. ' * 12
                     + 'Nguồn gốc nhận thức luận là cách xem xét phiến diện quá trình nhận thức.')

    def test_long_prose_uses_exact_sentence_spans_not_a_whole_mixed_paragraph(self):
        context = replace(self.context, text=self.long)
        units = build_evidence_units([context])
        self.assertGreater(len(units), 1)
        self.assertTrue(all(unit['text'] in context.text for unit in units))
        self.assertTrue(units[-1]['text'].startswith('Nguồn gốc nhận thức luận'))
        self.assertNotIn(self.long, [unit['text'] for unit in units])

    def test_short_lines_keep_existing_request_local_ids(self):
        context = replace(self.context, text='Khái niệm.\nNguồn gốc.')
        self.assertEqual([unit['evidence_id'] for unit in build_evidence_units([context])], ['E1.1', 'E1.2'])

    def test_numbered_procedure_keeps_whole_step_line(self):
        context = replace(self.context, text='Quy trình\n1. ' + self.long + '\n2. Hoàn tất.')
        units = build_evidence_units([context])
        self.assertEqual(len(units), 3)
        self.assertEqual(units[1]['text'], '1. ' + self.long)

    def test_unnumbered_procedure_keeps_whole_step_line(self):
        context = replace(self.context, text='Các bước sau:\n' + self.long + '\nHoàn tất.')
        self.assertEqual(len(build_evidence_units([context])), 3)

    def test_continued_or_ordinal_source_does_not_rebind_coverage_ids(self):
        for text in ['Quy trình (tiếp theo)\n' + self.long,
                     'Mặt thứ nhất: ' + self.long + '\nMặt thứ hai: Khả năng nhận thức.']:
            with self.subTest(text=text[:30]):
                self.assertEqual(len(build_evidence_units([replace(self.context, text=text)])), 2)

    def test_atomic_span_maps_back_to_its_original_citation_source(self):
        second = replace(self.context, source_id='S2', chunk_id='second', text=self.long)
        contexts = [self.context, second]
        last = build_evidence_units(contexts)[-1]
        raw = json.dumps({'items': [dict(text=last['text'], evidence_id=last['evidence_id'])]})
        self.assertEqual(render_structured_answer(raw, contexts, require_proof=True), last['text'] + ' [2]')


class DescriptionCoverageTests(TestCase):
    def setUp(self):
        fixture = fixtures.RAGPipelineTests()
        fixture.setUp()
        self.first = replace(fixture.first, page_number=7, text=(
            '+ Phương pháp xử lý trực tiếp là hình thức đầu tiên.\n'
            'Từng yêu cầu được xử lý ngay khi nhận.\n'
            '+ Phương pháp xử lý theo lô là hình thức thứ hai, trong\n7'))
        self.second = replace(self.first, source_id='S2', chunk_id='next', page_number=8, text=(
            'đó các yêu cầu được gom lại rồi xử lý cùng nhau.\n'
            '+ Phương pháp xử lý kết hợp là hình thức thứ ba.\n'
            'Hệ thống lựa chọn cách xử lý tùy từng nhóm yêu cầu.'))
        self.contexts = [self.first, self.second]
        self.question = 'Trình bày đặc điểm từng phương pháp xử lý theo học liệu.'

    def raw(self, ids):
        return json.dumps({'items': [dict(text='Một ý.', evidence_id=value) for value in ids]})

    def test_plan_contains_actual_description_spans_across_pages(self):
        groups = description_evidence_groups(self.question, self.contexts)
        self.assertEqual([g['required_evidence_id'] for g in groups], ['E1.2', 'E2.1', 'E2.3'])

    def test_names_only_are_not_a_complete_description(self):
        with self.assertRaises(GenerationError) as caught:
            validate_description_coverage(self.question, self.raw(['E1.1', 'E1.3', 'E2.2']), self.contexts)
        self.assertEqual(caught.exception.validation_reason, 'INCOMPLETE_ENUMERATION')
        self.assertEqual(len(caught.exception.missing_evidence), 3)

    def test_all_description_spans_are_accepted(self):
        validate_description_coverage(self.question, self.raw(['E1.2', 'E2.1', 'E2.3']), self.contexts)

    def test_narrow_or_names_only_question_has_no_forced_description(self):
        for question in ['Có các phương pháp xử lý nào?', 'Phương pháp xử lý trực tiếp là gì?']:
            self.assertEqual(description_evidence_groups(question, self.contexts), [])

    def test_no_forced_completion_for_insufficient_evidence(self):
        validate_description_coverage(self.question, '{"items":[]}', self.contexts)

    def test_other_document_cannot_supply_a_page_continuation(self):
        wrong = replace(self.second, document_id='11111111-1111-4111-8111-111111111111')
        self.assertEqual(description_evidence_groups(self.question, [self.first, wrong]), [])

    def test_other_version_cannot_supply_a_page_continuation(self):
        wrong = replace(self.second, version_id='11111111-1111-4111-8111-111111111111')
        self.assertEqual(description_evidence_groups(self.question, [self.first, wrong]), [])

    def test_nonadjacent_page_cannot_supply_a_continuation(self):
        wrong = replace(self.second, page_number=10)
        self.assertEqual(description_evidence_groups(self.question, [self.first, wrong]), [])

    def test_explanatory_dash_in_continuation_is_not_a_new_heading(self):
        second = replace(self.second, text=self.second.text.replace(
            'đó các yêu cầu', 'đó cách tiếp cận - phương pháp gom nhóm - cho phép các yêu cầu'))
        groups = description_evidence_groups(self.question, [self.first, second])
        self.assertEqual(len(groups), 3)

    def test_unrelated_bullet_topic_does_not_pollute_the_plan(self):
        noise = replace(self.second, source_id='S3', chunk_id='noise', page_number=12,
                        text='+ Phương pháp nghiên cứu khác là một cách nghiên cứu.\nNó có mục tiêu khác.')
        self.assertEqual(len(description_evidence_groups(self.question, [*self.contexts, noise])), 3)

    def test_retrieval_rank_need_not_match_adjacent_page_order(self):
        noise = replace(self.second, source_id='S3', chunk_id='noise', page_number=12, text='Nội dung khác.')
        groups = description_evidence_groups(self.question, [self.first, noise, self.second])
        self.assertEqual([g['required_evidence_id'] for g in groups], ['E1.2', 'E3.1', 'E3.3'])

    def test_description_prompt_and_bounded_retry_use_current_source_ids(self):
        class Constrained(SequenceProvider):
            def generate(inner, messages, *, timeout_seconds=None, json_schema=None):
                return super().generate(messages, timeout_seconds=timeout_seconds)
        provider = Constrained([json.dumps({'evidence_ids': ['E1.1']}),
                                json.dumps({'evidence_ids': ['E1.2', 'E2.1', 'E2.3']})])
        result = RAGPipeline(provider).generate_answer(question=self.question, mode='qa',
                                                       contexts=self.contexts, history=[])
        self.assertEqual(result.status, 'ANSWERED')
        self.assertEqual(result.trace.answer_origin, 'source_selected_extract')
        self.assertEqual(provider.generate_calls, 2)
        payload = json.loads(provider.requests[0][-1]['content'])
        self.assertEqual(len(payload['description_groups']), 3)
        feedback = json.loads(provider.requests[1][-1]['content'])['repair_feedback']
        self.assertEqual(feedback['required_evidence_ids'], ['E1.2', 'E2.1', 'E2.3'])


class CopiedClaimSourceTests(TestCase):
    def setUp(self):
        fixture = fixtures.RAGPipelineTests()
        fixture.setUp()
        self.claim = ('Các yêu cầu trong hàng đợi được gom thành những nhóm riêng biệt theo thời điểm tiếp nhận '
                      'và sau đó được xử lý lần lượt khi tài nguyên hệ thống đã sẵn sàng phục vụ công việc.')
        self.first = replace(fixture.first, text='Khái niệm ban đầu.\nPhần tiếp theo trình bày các nguyên tắc tổ chức.')
        self.second = replace(self.first, source_id='S2', chunk_id='next', page_number=2, text=self.claim)
        self.contexts = [self.first, self.second]

    def raw(self, evidence_id, text=None):
        return json.dumps({'items': [dict(text=text or self.claim, evidence_id=evidence_id)]})

    def test_copied_paragraph_cannot_be_assigned_to_introductory_source(self):
        with self.assertRaises(GenerationError) as caught:
            validate_copied_claim_sources(self.raw('E1.1'), self.contexts)
        self.assertEqual(caught.exception.validation_reason, 'EVIDENCE_QUOTE_MISMATCH')

    def test_correct_source_is_accepted_without_rebinding(self):
        validate_copied_claim_sources(self.raw('E2.1'), self.contexts)

    def test_shared_text_in_selected_source_is_not_rejected(self):
        contexts = [replace(self.first, text=self.claim), self.second]
        validate_copied_claim_sources(self.raw('E1.1'), contexts)

    def test_short_and_paraphrased_claims_are_not_falsely_certified_or_blocked(self):
        for text in ['Gom công việc theo nhóm.', 'Hệ thống đợi tài nguyên để thực thi những công việc đã nhận.']:
            validate_copied_claim_sources(self.raw('E1.1', text), self.contexts)

    def test_refusal_does_not_require_a_source(self):
        validate_copied_claim_sources('{"items":[]}', self.contexts)

    def test_retry_reselects_source_and_receives_specific_feedback(self):
        class Constrained(SequenceProvider):
            def generate(inner, messages, *, timeout_seconds=None, json_schema=None):
                return super().generate(messages, timeout_seconds=timeout_seconds)
        provider = Constrained([self.raw('E1.1'), json.dumps({'evidence_ids': ['E2.1']})])
        result = RAGPipeline(provider).generate_answer(question='Hệ thống xử lý yêu cầu như thế nào?', mode='qa',
                                                       contexts=self.contexts, history=[])
        self.assertEqual(result.status, 'ANSWERED')
        self.assertEqual(provider.generate_calls, 2)
        self.assertEqual(result.references[0].source_id, self.second.source_id)
        self.assertEqual(result.trace.answer_origin, 'source_selected_extract')
        feedback = json.loads(provider.requests[1][-1]['content'])['repair_feedback']
        self.assertEqual(feedback['validation_reason'], 'EVIDENCE_QUOTE_MISMATCH')
        self.assertNotIn('required_evidence_ids', feedback)


class SourceSelectionTests(TestCase):
    def setUp(self):
        fixture = fixtures.RAGPipelineTests()
        fixture.setUp()
        self.context = replace(fixture.first, text='Mỗi nhóm yêu cầu được xử lý khi tài nguyên đã sẵn sàng.')

    def render(self, raw):
        return render_source_selection(raw, [self.context], 'Yêu cầu được xử lý khi nào?')

    def test_answer_is_literal_source_not_free_model_text(self):
        answer = self.render('{"evidence_ids":["E1.1"]}')
        self.assertIn(self.context.text + ' [1]', answer)
        self.assertTrue(answer.startswith('Trích học liệu:'))

    def test_model_cannot_supply_an_answer_in_selection_protocol(self):
        for raw in ['{"evidence_ids":["E1.1"],"text":"Nội dung tự tạo."}',
                    '{"items":[{"text":"Tự tạo.","evidence_id":"E1.1"}]}']:
            with self.assertRaises(GenerationError):
                self.render(raw)

    def test_unknown_duplicate_or_nonstring_ids_fail_closed(self):
        for ids in [['E9.1'], ['E1.1', 'E1.1'], [None], [1], ['E1.1'] * 13]:
            with self.assertRaises(GenerationError):
                self.render(json.dumps({'evidence_ids': ids}))

    def test_duplicate_json_keys_are_not_accepted(self):
        with self.assertRaises(GenerationError):
            self.render('{"evidence_ids":[],"evidence_ids":["E1.1"]}')

    def test_empty_selection_refuses_without_forcing_a_source(self):
        self.assertEqual(self.render('{"evidence_ids":[]}'), 'INSUFFICIENT_EVIDENCE')

    def test_page_number_and_introduction_are_not_an_answer(self):
        for text in ['8', 'Các điều kiện sau đây:', 'Đây là một câu chưa hoàn chỉnh nên trong']:
            with self.subTest(text=text), self.assertRaises(GenerationError):
                render_source_selection('{"evidence_ids":["E1.1"]}',
                                        [replace(self.context, text=text)], 'Điều kiện nào?')

    def test_schema_only_allows_current_source_ids_not_answer_text(self):
        schema = source_selection_schema(['E1.1', 'E2.1'])
        self.assertEqual(schema['required'], ['evidence_ids'])
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(schema['properties']['evidence_ids']['items']['enum'], ['E1.1', 'E2.1'])
