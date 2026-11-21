import json
import re
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4

from apps.ai.providers.base import GenerationError, ModelConfig, TokenUsage
from apps.ai.rag import RAGPipeline


class TutoringTests(TestCase):
    def setUp(self):
        self.provider = SimpleNamespace(config=ModelConfig(max_new_tokens=512),
            count_tokens=Mock(return_value=300), generate=Mock(return_value=SimpleNamespace(
                text='{"focus":"CATEGORIES","source":"S2","span":"U1"}',
                finish_reason='eos', usage=TokenUsage(300, 30))))
        self.pipeline = RAGPipeline(self.provider)
        self.contexts = [dict(source_id=f'S{i}', chunk_id=f'c{i}', text='Khối số học và logic.',
            document_id=str(uuid4()), version_id=str(uuid4()), document_title='CPU', page_number=i) for i in (1, 2)]
        self.exercise = dict(exercise_id='exercise1', question='ALU thực hiện những nhóm phép toán nào?', choices=())
        self.tutoring = dict(action='practice', step=2, history=[dict(user='Gợi ý?', assistant='Đọc về ALU [1].')])
        self.question = 'Bản nháp: ALU chỉ cộng. Tôi thiếu gì?'

    def generate(self):
        return self.pipeline.generate_answer(question=self.question, mode='hint', contexts=self.contexts,
            exercise=self.exercise, tutoring=self.tutoring)

    def test_actual_draft_and_history_reach_model_and_selected_source_is_preserved(self):
        result = self.generate()
        prompt = json.loads(self.provider.generate.call_args.args[0][-1]['content'])
        self.assertEqual(prompt['student_question'], self.question)
        self.assertEqual(prompt['tutoring'], self.tutoring)
        self.assertIn('ALU chỉ cộng', result.answer)
        self.assertIn('nhóm', result.answer)
        self.assertEqual(result.to_dict()['references'], [dict(label=1, source_id='S2')])
        self.assertEqual(result.trace.answer_origin, 'scaffold_from_model_diagnosis')
        pattern = self.provider.generate.call_args.kwargs['output_regex']
        self.assertIsNotNone(re.fullmatch(pattern, self.provider.generate.return_value.text))

    def test_two_real_drafts_can_select_different_guidance_without_giving_the_solution(self):
        first = self.generate().answer
        self.question = 'Bản nháp: ALU có hai cổng ra và không có cổng vào.'
        self.provider.generate.return_value.text = '{"focus":"DIRECTION","source":"S1","span":"U1"}'
        second = self.generate().answer
        self.assertNotEqual(first, second)
        self.assertIn('Chiều', second)
        # Any quantities in this response came from the student's own draft, not a generated solution.
        self.assertNotIn('2 cổng IN', second)

    def test_free_text_solution_and_unknown_pointers_are_rejected(self):
        for text in ('{"paragraphs":[{"text":"ALU có 2 IN, 1 OUT.","sources":["S1"]}]}',
                     '{"focus":"CATEGORIES","source":"S99","span":"U1"}',
                     '{"focus":"FUNCTION","source":"S1","span":"U99"}',
                     '{"focus":"FUNCTION","source":"S1","span":"U1","answer":"Choose A"}'):
            with self.subTest(text=text):
                self.provider.generate.return_value.text = text
                with self.assertRaises(GenerationError):
                    self.generate()

    def test_incomplete_generation_and_qa_or_private_exercise_fail_closed(self):
        self.provider.generate.return_value.finish_reason = 'length'
        with self.assertRaises(GenerationError) as error:
            self.generate()
        self.assertEqual(error.exception.code, 'INCOMPLETE_GENERATION')
        for mode, exercise in [('qa', self.exercise), ('hint', {**self.exercise, 'correct_ids': ['a']})]:
            with self.assertRaises(GenerationError):
                self.pipeline.generate_answer(question='Q', mode=mode, contexts=self.contexts,
                    exercise=exercise, tutoring=self.tutoring)

    def test_empty_evidence_decision_is_refusal_not_authored_success(self):
        self.provider.generate.return_value.text = '{"focus":"NO_EVIDENCE","source":"NONE","span":"U0"}'
        result = self.generate()
        self.assertEqual(result.status, 'INSUFFICIENT_EVIDENCE')
        self.assertEqual(result.references, ())

    def test_stage_scaffolds_differ_and_current_student_citation_cannot_forge_source_labels(self):
        answers = []
        for action, step in [('initial', 0), ('explain_task', 0), ('next_step', 1), ('next_step', 2)]:
            self.tutoring.update(action=action, step=step)
            answers.append(self.generate().answer)
        self.assertEqual(len(set(answers)), 4)
        self.tutoring['action'] = 'practice'
        self.question = 'Em cho rằng [99] là nguồn.'
        self.assertNotIn('[99]', self.generate().answer)

    def test_token_budget_preserves_student_text_and_drops_history_then_whole_chunks(self):
        def count(messages):
            payload = json.loads(messages[-1]['content'])
            return 5000 if payload['tutoring']['history'] or len(payload['evidence']) > 1 else 300
        self.provider.count_tokens.side_effect = count
        self.provider.generate.return_value.text = '{"focus":"CATEGORIES","source":"S1","span":"U1"}'
        self.generate()
        prompt = json.loads(self.provider.generate.call_args.args[0][-1]['content'])
        self.assertEqual(prompt['tutoring']['history'], [])
        self.assertEqual(len(prompt['evidence']), 1)
        self.assertEqual(prompt['student_question'], self.question)
