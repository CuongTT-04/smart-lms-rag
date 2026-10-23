from uuid import uuid4
from django.test import SimpleTestCase
from apps.ai.api.serializers import ChatRequest


class ChatContractTests(SimpleTestCase):
    def values(self, **extra):
        return {'question': ' Nội dung tài liệu? ', 'course_id': str(uuid4()), **extra}

    def test_defaults_and_null_or_empty_document_selection(self):
        for selection in (None, []):
            serializer = ChatRequest(data=self.values(document_ids=selection))
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertEqual(serializer.validated_data['document_ids'], selection)
            self.assertEqual(serializer.validated_data['mode'], 'qa')

    def test_query_boundaries_and_unknown_fields(self):
        for extra in ({'question': ''}, {'question': '   '}, {'question': 'a'*8001},
                      {'mode': None}, {'mode': 'other'}, {'course_id': 'bad'},
                      {'allowed_version_ids': []}, {'preview': True}, {'user_id': str(uuid4())}):
            serializer = ChatRequest(data=self.values(**extra))
            self.assertFalse(serializer.is_valid(), extra)
        serializer = ChatRequest(data=self.values(question='a'*8000))
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_hint_requires_assessment_and_qa_disallows_exercise(self):
        for extra in ({'mode': 'hint'}, {'question_id': str(uuid4())},
                      {'assessment_id': str(uuid4())}):
            self.assertFalse(ChatRequest(data=self.values(**extra)).is_valid())
        self.assertTrue(ChatRequest(data=self.values(mode='hint', assessment_id=str(uuid4()))).is_valid())
