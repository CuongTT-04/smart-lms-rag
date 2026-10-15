from dataclasses import asdict
from uuid import uuid4
from django.test import SimpleTestCase
from apps.documents.processors.chunker import chunk_extraction, normalize_page
from apps.documents.retrieval_contracts import ChunkingConfig


class CharacterTokenizer:
    def encode(self, text, add_special_tokens=False):
        return list(range(len(text)))
    def __call__(self, text, **kwargs):
        return {'offset_mapping': [(i, i+1) for i in range(len(text))]}


def envelope(*pages):
    return {'schema_version':'1.0', 'course_id':str(uuid4()),
            'document_id':str(uuid4()), 'version_id':str(uuid4()),
            'checksum_sha256':'a'*64, 'page_count':len(pages),
            'pages':[{'page_number':i+1,'text':p,'status':'OK'} for i,p in enumerate(pages)]}


class ChunkerTests(SimpleTestCase):
    def setUp(self):
        self.config=ChunkingConfig(tokenizer_revision='test-revision', max_tokens=32, overlap_tokens=4)
        self.tokenizer=CharacterTokenizer()

    def test_offsets_coverage_stable_ids_and_no_cross_page(self):
        data=envelope('Xin cha\u0300o. '+'x'*140, 'Trang hai '+ 'b'*60)
        chunks=chunk_extraction(data,'Tài liệu',self.config,self.tokenizer)
        self.assertEqual(chunks,chunk_extraction(data,'Tài liệu',self.config,self.tokenizer))
        self.assertEqual(len({c.chunk_id for c in chunks}),len(chunks))
        for page in data['pages']:
            text=normalize_page(page['text']); selected=[c for c in chunks if c.page_number==page['page_number']]
            covered=set()
            for c in selected:
                self.assertEqual(c.text,text[c.char_start:c.char_end])
                self.assertLessEqual(c.token_count,32)
                covered.update(range(c.char_start,c.char_end))
            self.assertTrue({i for i,x in enumerate(text) if not x.isspace()} <= covered)

    def test_blank_page_and_unicode_normalization(self):
        chunks=chunk_extraction(envelope(' \n ', 'e\u0301\r\nA'),'PDF',self.config,self.tokenizer)
        self.assertEqual(len(chunks),1)
        self.assertEqual(chunks[0].page_number,2)
        self.assertEqual(chunks[0].text,'é\nA')
        self.assertIsNone(chunks[0].section_title)

    def test_config_change_changes_ids(self):
        data=envelope('word '*20)
        first=chunk_extraction(data,'PDF',self.config,self.tokenizer)
        second=chunk_extraction(data,'PDF',ChunkingConfig(tokenizer_revision='test-revision',max_tokens=24,overlap_tokens=4),self.tokenizer)
        self.assertNotEqual(first[0].chunk_id,second[0].chunk_id)

    def test_invalid_configuration_and_envelope_fail_closed(self):
        for kwargs in [{'max_tokens':0},{'max_tokens':4,'overlap_tokens':4},{'tokenizer_revision':''}]:
            with self.assertRaises(ValueError): ChunkingConfig(**{'tokenizer_revision':'test', **kwargs})
        data=envelope('text'); data['pages'][0]['page_number']=2
        with self.assertRaises(ValueError): chunk_extraction(data,'PDF',self.config,self.tokenizer)

    def test_json_serialization(self):
        chunk=chunk_extraction(envelope('abc'),'PDF',self.config,self.tokenizer)[0]
        self.assertEqual(asdict(chunk)['schema_version'],'1.0')
