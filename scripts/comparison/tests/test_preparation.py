from copy import deepcopy
import unittest

from scripts.comparison.audit_preparation import check_context
from scripts.comparison.protocol import digest


class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.source = dict(chunk_id='c1', text='source passage', course_id='course1',
            document_id='doc1', version_id='version1', source_checksum='a'*64,
            page_number=2, char_start=10, char_end=24)
        self.chunks = {'c1': self.source}
        context = deepcopy(self.source)
        context['rank'] = 1
        self.cache = dict(scope_id='course1', contexts=[context], packing=dict(
            retrieved_chunks=[dict(chunk_id='c1', document_id='doc1', page_number=2,
                                   text_sha256=digest(self.source['text']))]))

    def test_exact_source(self):
        check_context(self.cache, self.chunks)

    def test_valid_truncated_prefix(self):
        self.cache['contexts'][0].update(text='source', packed_char_end=16)
        check_context(self.cache, self.chunks)

    def test_cross_course_rejected(self):
        self.cache['scope_id'] = 'course2'
        with self.assertRaisesRegex(ValueError, 'CROSS_COURSE'):
            check_context(self.cache, self.chunks)

    def test_invented_context_rejected(self):
        self.cache['contexts'][0]['text'] = 'invented'
        with self.assertRaisesRegex(ValueError, 'NOT_SOURCE_PREFIX'):
            check_context(self.cache, self.chunks)

    def test_changed_source_hash_rejected(self):
        self.cache['packing']['retrieved_chunks'][0]['text_sha256'] = 'b'*64
        with self.assertRaisesRegex(ValueError, 'SOURCE_BINDING'):
            check_context(self.cache, self.chunks)

    def test_incorrect_truncation_offset_rejected(self):
        self.cache['contexts'][0].update(text='source', packed_char_end=15)
        with self.assertRaisesRegex(ValueError, 'PACKED_END'):
            check_context(self.cache, self.chunks)


if __name__ == '__main__':
    unittest.main()
