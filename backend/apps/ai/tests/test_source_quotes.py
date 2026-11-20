from copy import deepcopy
from unittest import TestCase

from apps.ai.source_quotes import complete_quote_context


class QuoteContextTests(TestCase):
    def setUp(self):
        self.previous = 'Cách thứ nhất xử lý riêng từng yêu cầu để giảm thời gian chờ.'
        self.transition = 'Bên cạnh cách thứ nhất, hệ thống còn có cách xử lý theo'
        self.following = 'lô. Các yêu cầu được tập hợp và xử lý cùng nhau khi có đủ tài nguyên.'
        identity = dict(document_id='11111111-1111-4111-8111-111111111111',
                        version_id='22222222-2222-4222-8222-222222222222', document_title='Học liệu')
        self.citations = [dict(identity, label=1, chunk_id='first', page_number=4,
                               excerpt=self.previous + '\n' + self.transition + '\n4'),
                          dict(identity, label=2, chunk_id='second', page_number=5, excerpt=self.following)]
        self.answer = f'Trích học liệu:\n\n1. {self.transition} [1]\n2. {self.following} [2]'

    def test_wrap_and_antecedent_are_completed_with_literal_source(self):
        answer = complete_quote_context(self.answer, self.citations)
        self.assertIn('1. ' + self.previous + ' [1]', answer)
        self.assertIn('2. ' + self.transition + ' [1] ' + self.following + ' [2]', answer)

    def test_free_form_answer_is_untouched(self):
        answer = 'Hệ thống xử lý theo nhóm. [2]'
        self.assertEqual(complete_quote_context(answer, self.citations), answer)

    def test_nonliteral_text_cannot_trigger_expansion(self):
        answer = self.answer.replace('cách thứ nhất', 'một đáp án tự tạo')
        self.assertEqual(complete_quote_context(answer, self.citations), answer)

    def test_other_document_version_or_page_cannot_continue_a_quote(self):
        for key, value in [('document_id', 'different'), ('version_id', 'different'), ('page_number', 7)]:
            citations = deepcopy(self.citations)
            citations[1][key] = value
            self.assertEqual(complete_quote_context(self.answer, citations), self.answer)

    def test_unknown_citation_is_untouched(self):
        answer = self.answer.replace('[2]', '[9]')
        self.assertEqual(complete_quote_context(answer, self.citations), answer)

    def test_complete_sentence_is_not_expanded(self):
        citations = deepcopy(self.citations)
        citations[0]['excerpt'] = citations[0]['excerpt'].replace(self.transition, self.transition + '.')
        answer = self.answer.replace(self.transition, self.transition + '.')
        self.assertEqual(complete_quote_context(answer, citations), answer)

    def test_previous_heading_is_not_promoted_to_answer_content(self):
        citations = deepcopy(self.citations)
        citations[0]['excerpt'] = '+ Tiêu đề của phần tiếp theo.\n' + self.transition
        self.assertEqual(complete_quote_context(self.answer, citations), self.answer)

    def test_already_selected_antecedent_is_not_duplicated(self):
        answer = f'Trích học liệu:\n\n1. {self.previous} [1]\n2. {self.transition} [1]\n3. {self.following} [2]'
        completed = complete_quote_context(answer, self.citations)
        self.assertEqual(completed.count(self.previous), 1)
        self.assertEqual(len(completed.splitlines()), 4)

    def test_malformed_list_is_not_rewritten(self):
        answer = self.answer.replace('2. ', '4. ')
        self.assertEqual(complete_quote_context(answer, self.citations), answer)
