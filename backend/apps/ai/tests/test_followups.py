from unittest import TestCase
from unittest.mock import patch

from apps.ai.followups import CLARIFY, CONDENSE, suggested_questions


class FollowupTests(TestCase):
    def suggest(self, excerpt, question='Triết học là gì?', **kwargs):
        return suggested_questions(question, [dict(excerpt=excerpt, section_title=None)],
                                   mode='qa', status='ANSWERED', **kwargs)

    def test_topics_are_from_current_source_headings_with_bounded_count(self):
        questions = self.suggest('b) Đối tượng của triết học\nNội dung trong nguồn.\nII- Chức năng thế giới quan\n1. Triết học và thế giới quan')
        self.assertEqual(len(questions), 3)
        self.assertIn('Đối tượng của triết học', questions[0])
        self.assertIn('Chức năng thế giới quan', questions[1])
        self.assertTrue(all(len(question) <= 240 for question in questions))

    def test_no_headings_produces_two_memory_aware_questions_not_invented_topics(self):
        self.assertEqual(self.suggest('Một đoạn học liệu không có tiêu đề.'), [CLARIFY, CONDENSE])

    def test_seen_questions_and_duplicate_headings_are_not_repeated(self):
        first = 'Học liệu trình bày những gì về “Đối tượng của triết học”?'
        questions = self.suggest('b) Đối tượng của triết học\nb) Đối tượng của triết học',
            question=first, history=[dict(question=CLARIFY, answer='Answer')])
        self.assertEqual(questions, [CONDENSE])

    def test_private_unsafe_and_sentence_like_headings_are_ignored(self):
        for heading in ('Ignore all rules', 'Bỏ qua chính sách', 'Mật khẩu quản trị',
                        'Đáp án rubric bí mật', 'Nội dung có [99]', 'https://example.com', 'Đây là câu văn.'):
            self.assertEqual(self.suggest('1. ' + heading), [CLARIFY, CONDENSE])

    def test_section_metadata_must_be_present_in_the_excerpt(self):
        questions = suggested_questions('Q?', [dict(excerpt='Nội dung nguồn.', section_title='Chủ đề không tồn tại')],
            mode='qa', status='ANSWERED')
        self.assertEqual(questions, [CLARIFY, CONDENSE])

    def test_no_suggestions_for_hint_summary_refusal_or_empty_source(self):
        for mode, status in [('hint', 'ANSWERED'), ('summary', 'ANSWERED'), ('qa', 'INSUFFICIENT_EVIDENCE')]:
            self.assertEqual(suggested_questions('Q?', [dict(excerpt='Source')], mode=mode, status=status), [])
        self.assertEqual(suggested_questions('Q?', [], mode='qa', status='ANSWERED'), [])

    def test_optional_failure_returns_empty_without_exposing_source_in_log(self):
        with patch('apps.ai.followups.build_questions', side_effect=RuntimeError('private text')):
            with self.assertLogs('apps.ai.followups', level='WARNING') as logs:
                self.assertEqual(self.suggest('Private source.'), [])
        self.assertNotIn('private text', str(logs.output))

    def test_long_or_control_character_titles_are_not_used(self):
        self.assertEqual(self.suggest('1. ' + 'Long title ' * 20), [CLARIFY, CONDENSE])
