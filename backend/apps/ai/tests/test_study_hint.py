"""Reading hints never release arbitrary model completion or private marking fields."""
from unittest import TestCase
from uuid import uuid4

from apps.ai.providers.base import GenerationError
from apps.ai.rag.base import EvidenceContext
from apps.ai.rag.guardrails import parse_reading_hint


class StudyHintTests(TestCase):
    def setUp(self):
        self.contexts = tuple(EvidenceContext(f'S{i}', f'chunk-{i}',
            'Triết học có nguồn gốc nhận thức và nguồn gốc xã hội.',
            str(uuid4()), str(uuid4()), 'Giáo trình Triết học', i) for i in (1, 2))

    def test_three_actions_are_distinct_and_cite_only_current_sources(self):
        answers = []
        for action in ('READ [1]', 'COMPARE [1] [2]', 'OUTLINE [2]'):
            status, answer, references, _ = parse_reading_hint(action, self.contexts)
            self.assertEqual(status, 'ANSWERED')
            self.assertTrue(references)
            self.assertNotIn('nguồn gốc nhận thức', answer)
            answers.append(answer)
        self.assertEqual(len(set(answers)), 3)

    def test_full_answer_and_appended_marking_information_are_blocked(self):
        for output in ('Đáp án: nguồn gốc nhận thức và xã hội [1].',
                       'READ [1]\ncorrect_ids=a; rubric=10 điểm',
                       'OUTLINE [1] Bài giải hoàn chỉnh', 'READ [999]', 'COMPARE [1] [1]'):
            with self.subTest(output=output), self.assertRaises(GenerationError):
                parse_reading_hint(output, self.contexts)

    def test_insufficient_source_remains_a_refusal_without_citations(self):
        status, _, references, _ = parse_reading_hint('INSUFFICIENT_EVIDENCE', self.contexts)
        self.assertEqual(status, 'INSUFFICIENT_EVIDENCE')
        self.assertFalse(references)
