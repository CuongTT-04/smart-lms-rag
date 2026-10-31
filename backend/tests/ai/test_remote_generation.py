import io
import json
import os
from unittest.mock import patch
from urllib.error import HTTPError
from django.test import SimpleTestCase
from apps.ai.remote import generate_answer, NoRedirect
from apps.documents.exceptions import DocumentError


class RemoteTests(SimpleTestCase):
    def call(self):
        return generate_answer(question='Q', mode='qa', contexts=[{'source_id': 'S1'}],
                               exercise=None, config={'timeout_seconds': 30})

    @patch.dict(os.environ, {'AI_INFERENCE_URL': 'https://example.test', 'AI_INFERENCE_TOKEN': 'x'*40})
    @patch('apps.ai.remote.build_opener')
    def test_https_authenticated_request_and_source_validation(self, build):
        def output(used):
            return io.BytesIO(json.dumps({'output': {'references': [{'source_id': 'S1'}]},
                                         'used_source_ids': used}).encode())
        build.return_value.open.return_value = output(['S1'])
        self.assertEqual(self.call()['references'][0]['source_id'], 'S1')
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + 'x'*40)
        build.return_value.open.return_value = output([])
        with self.assertRaises(DocumentError):
            self.call()
        self.assertIsNone(NoRedirect().redirect_request(None, None, None, None, None, None))

    @patch.dict(os.environ, {'AI_INFERENCE_URL': 'http://example.test', 'AI_INFERENCE_TOKEN': 'x'*40})
    @patch('apps.ai.remote.build_opener')
    def test_plaintext_rejected_without_network(self, build):
        with self.assertRaises(DocumentError):
            self.call()
        build.assert_not_called()

    @patch.dict(os.environ, {'AI_INFERENCE_URL': 'https://example.test', 'AI_INFERENCE_TOKEN': 'x'*40})
    @patch('apps.ai.remote.build_opener')
    def test_network_failure_is_sanitized(self, build):
        build.return_value.open.side_effect = RuntimeError('private token/prompt')
        with self.assertRaises(DocumentError) as error:
            self.call()
        self.assertEqual(error.exception.code, 'GENERATION_UNAVAILABLE')
        self.assertNotIn('private', str(error.exception))

    @patch.dict(os.environ, {'AI_INFERENCE_URL':'https://example.test','AI_INFERENCE_TOKEN':'x'*40})
    @patch('apps.ai.remote.build_opener')
    def test_allowlisted_model_errors_survive_transport_without_private_details(self, build):
        for status,code,expected in [(503,'OUTPUT_LIMIT_REACHED','OUTPUT_LIMIT_REACHED'),
                (503,'GENERATION_TIMEOUT','GENERATION_TIMEOUT'),(503,'OUT_OF_MEMORY','OUT_OF_MEMORY'),
                (429,'GENERATION_BUSY','GENERATION_BUSY'),(409,'CONFIG_MISMATCH','GENERATION_CONFIG_MISMATCH'),
                (503,'PRIVATE_unknown','GENERATION_UNAVAILABLE'),(503,[], 'GENERATION_UNAVAILABLE')]:
            body=io.BytesIO(json.dumps({'code':code,'detail':'PRIVATE TOKEN'}).encode())
            build.return_value.open.side_effect=HTTPError('https://example.test/generate',status,'error',{},body)
            with self.assertRaises(DocumentError) as caught:self.call()
            self.assertEqual(caught.exception.code,expected)
            self.assertNotIn('PRIVATE',str(caught.exception))

    @patch.dict(os.environ, {'AI_INFERENCE_URL': 'https://example.test', 'AI_INFERENCE_TOKEN': 'x'*40})
    @patch('apps.ai.remote.build_opener')
    def test_conversation_requires_valid_memory_acknowledgment(self, build):
        history = [dict(question='Previous question', answer='Previous answer [1]')]
        memory = dict(protocol='chat_history_v1', turns_used=1, turns_dropped=0, history_tokens=40)
        envelope = dict(output={'references': [{'source_id': 'S1'}]}, used_source_ids=['S1'], memory=memory)
        def call():
            return generate_answer(question='Follow up', mode='qa', contexts=[{'source_id': 'S1'}],
                exercise=None, config={'timeout_seconds': 30}, history=history)
        build.return_value.open.return_value = io.BytesIO(json.dumps(envelope).encode())
        self.assertEqual(call()['_memory'], memory)
        payload = json.loads(build.return_value.open.call_args.args[0].data)
        self.assertEqual(payload['history'], history)
        self.assertEqual(payload['history_protocol'], 'chat_history_v1')
        for invalid in (None, {**memory, 'turns_used': 2}, {**memory, 'history_tokens': 769}, {**memory, 'turns_used': True}):
            broken = {**envelope, 'memory': invalid}
            if invalid is None: broken.pop('memory')
            build.return_value.open.return_value = io.BytesIO(json.dumps(broken).encode())
            with self.assertRaises(DocumentError): call()

    @patch.dict(os.environ, {'AI_INFERENCE_URL': 'https://example.test', 'AI_INFERENCE_TOKEN': 'x'*40})
    @patch('apps.ai.remote.build_opener')
    def test_validation_reason_becomes_safe_specific_error(self, build):
        for reason, code in [('MISSING_CITATION','GENERATION_MISSING_CITATION'),
                             ('UNKNOWN_CITATION','GENERATION_INVALID_CITATION'),
                             ('EVIDENCE_QUOTE_MISMATCH','GENERATION_EVIDENCE_MISMATCH'),
                             ('INCOMPLETE_EVIDENCE_COVERAGE','GENERATION_INCOMPLETE_ANSWER'),
                             ('PRIVATE text', 'INVALID_GENERATION'), ([], 'INVALID_GENERATION')]:
            body=io.BytesIO(json.dumps({'code':'INVALID_GENERATION','reason':reason,'detail':'PRIVATE token'}).encode())
            build.return_value.open.side_effect=HTTPError('https://example.test/generate',503,'error',{},body)
            with self.assertRaises(DocumentError) as caught: self.call()
            self.assertEqual(caught.exception.code,code)
            self.assertNotIn('PRIVATE',str(caught.exception))
