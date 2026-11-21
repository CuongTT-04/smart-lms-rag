import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from apps.ai.providers.base import GenerationError
from apps.ai.rag.summary import step, response_schema, response_pattern, validate_paragraphs


class SummaryGenerationTests(TestCase):
    def provider(self, limit=3000):
        return SimpleNamespace(config=SimpleNamespace(max_input_tokens=limit,max_new_tokens=1024),
            count_tokens=lambda messages: len(messages[-1]['content']),
            generate=Mock(return_value=SimpleNamespace(text=json.dumps({'paragraphs':[{'text':'Bản tổng hợp mạch lạc.','sources':['S1']}]}))))

    def blocks(self):
        return [dict(id=f'B{i}',source_id=f'S{i}',text='Nội dung học liệu. '*20) for i in range(1,6)]

    def test_actual_token_budget_consumes_only_whole_prefix_blocks(self):
        provider=self.provider(1000)
        result=step(provider,'map',self.blocks())
        self.assertTrue(0 < result['consumed'] < 5)
        payload=json.loads(provider.generate.call_args.args[0][-1]['content'])
        self.assertEqual(payload['data'],self.blocks()[:result['consumed']])

    def test_does_not_generate_if_even_one_block_cannot_fit(self):
        provider=self.provider(1)
        with self.assertRaises(GenerationError): step(provider,'map',self.blocks())
        provider.generate.assert_not_called()

    def test_unknown_sources_or_embedded_citation_are_rejected(self):
        for paragraph in [dict(text='Wrong',sources=['S999']),dict(text='Fake [1]',sources=['S1']),
                          dict(text='Các nguồn tham khảo: S1, S2.', sources=['S1'])]:
            provider=self.provider()
            provider.generate.return_value.text=json.dumps(dict(paragraphs=[paragraph]))
            with self.assertRaises(GenerationError): step(provider,'map',self.blocks())

    def test_reduce_cannot_invent_sources_or_discard_all_notes(self):
        notes=[dict(paragraphs=[dict(text='Ý chính.',sources=['S1'])])]*2
        provider=self.provider()
        self.assertEqual(step(provider,'reduce',notes)['consumed'],2)
        provider.generate.return_value.text=json.dumps(dict(paragraphs=[]))
        with self.assertRaises(GenerationError): step(provider,'reduce',notes)

    def test_cover_only_map_can_be_empty_but_still_acknowledges_read_blocks(self):
        provider=self.provider()
        provider.generate.return_value.text=json.dumps(dict(paragraphs=[]))
        result=step(provider,'map',self.blocks())
        self.assertTrue(result['consumed']>0)
        self.assertEqual(result['paragraphs'],[])

    def test_repeated_known_sources_are_deduplicated_without_changing_text(self):
        provider=self.provider()
        text='Nội dung tổng hợp được giữ nguyên.'
        provider.generate.return_value.text=json.dumps(dict(paragraphs=[dict(text=text,sources=['S1','S1'])]))
        result=step(provider,'map',self.blocks())
        self.assertEqual(result['paragraphs'],[dict(text=text,sources=['S1'])])

    def test_validation_reasons_distinguish_text_from_unknown_sources(self):
        for paragraph,reason in [(dict(text='Theo S1.',sources=['S1']),'SUMMARY_EMBEDDED_CITATION'),
                                 (dict(text='Nội dung.',sources=['S99']),'SUMMARY_UNKNOWN_SOURCE')]:
            provider=self.provider()
            provider.generate.return_value.text=json.dumps(dict(paragraphs=[paragraph]))
            with self.assertRaises(GenerationError) as error: step(provider,'map',self.blocks())
            self.assertEqual(error.exception.validation_reason,reason)

    def test_decoding_schema_prevents_embedded_references_without_unsupported_length_combination(self):
        import re
        schema=response_schema(['S1','S2'])
        text=schema['properties']['paragraphs']['items']['properties']['text']
        self.assertNotIn('minLength',text)
        self.assertNotIn('maxLength',text)
        for value in ('Triết học là tri thức lý luận.', 'Sau đó, xem xét sự vận động.', 'Số 1024.', 'S'):
            self.assertIsNotNone(re.fullmatch(text['pattern'],value),value)
        for value in ('Câu trả lời [1].', 'Theo S1.', 'S12', 'Văn bản 中文', ''):
            self.assertIsNone(re.fullmatch(text['pattern'],value),value)

    def test_complete_json_grammar_has_bounded_arrays_and_known_sources(self):
        import re
        pattern=response_pattern(['S1','S2'],allow_empty=False)
        paragraph=dict(text='Nội dung tổng hợp.',sources=['S1'])
        encode=lambda paragraphs: json.dumps(dict(paragraphs=paragraphs),ensure_ascii=False,separators=(',',':'))
        self.assertIsNotNone(re.fullmatch(pattern,encode([paragraph]*6)))
        self.assertIsNone(re.fullmatch(pattern,encode([paragraph]*7)))
        self.assertIsNone(re.fullmatch(pattern,encode([dict(text='Nội dung.',sources=['S99'])])))
        self.assertIsNone(re.fullmatch(pattern,encode([dict(text='Nội dung.',sources=['S1']*13)])))
        self.assertIsNone(re.fullmatch(pattern,encode([])))
        self.assertIsNotNone(re.fullmatch(response_pattern(['S1'],allow_empty=True),encode([])))

    def test_json_quotes_and_backslashes_do_not_force_an_early_string_end(self):
        import re
        text='Thừa nhận cả "hoặc là" và "vừa là"; ký hiệu \\ được giữ nguyên.'
        schema=response_schema(['S1'])
        self.assertIsNotNone(re.fullmatch(schema['properties']['paragraphs']['items']['properties']['text']['pattern'],text))
        body=json.dumps(dict(paragraphs=[dict(text=text,sources=['S1'])]),ensure_ascii=False,separators=(',',':'))
        self.assertIsNotNone(re.fullmatch(response_pattern(['S1'],allow_empty=False),body))
        self.assertEqual(json.loads(body)['paragraphs'][0]['text'],text)

    def test_complete_json_is_not_enough_when_the_sentence_is_unfinished(self):
        for text in ('Phương pháp thừa nhận cả cái ', 'Ví dụ:', 'Mối liên hệ và'):
            with self.assertRaises(GenerationError) as caught:
                validate_paragraphs([dict(text=text,sources=['S1'])],{'S1'},require_complete=True)
            self.assertEqual(caught.exception.validation_reason,'SUMMARY_INCOMPLETE_SENTENCE')
        for text in ('Nội dung đã hoàn tất.', 'Gọi là "biện chứng."', 'Nội dung (đã hoàn tất.)'):
            validate_paragraphs([dict(text=text,sources=['S1'])],{'S1'},require_complete=True)
