import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest import TestCase

from apps.ai.inference_gateway import start_gateway


class GatewayTests(TestCase):
    def setUp(self):
        self.calls = []
        def generate(**data):
            self.calls.append(data)
            return SimpleNamespace(to_dict=lambda: {'status': 'ANSWERED', 'answer': 'A [1]',
                'references': [{'label': 1, 'source_id': 'S1'}], 'usage': None},
                trace=SimpleNamespace(used_source_ids=('S1',)))
        self.pipeline = SimpleNamespace(generate_answer=generate)
        self.server = start_gateway(self.pipeline, 'x' * 40, {'model': 'Qwen'}, port=0)
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def request(self, path='/generate', token='x' * 40, data=None):
        body = json.dumps(data or {'question': 'Q', 'mode': 'qa', 'contexts': [],
                                 'exercise': None, 'config': {'model': 'Qwen'}}).encode()
        return urlopen(Request(self.url + path, data=body if path == '/generate' else None,
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}), timeout=2)

    def test_auth_before_model_and_health(self):
        with self.assertRaises(HTTPError) as error:
            self.request(token='wrong')
        self.assertEqual(error.exception.code, 401)
        self.assertEqual(self.calls, [])
        with self.request('/health') as response:
            self.assertTrue(json.load(response)['ready'])

    def test_validation_reason_is_allowlisted_without_private_output(self):
        from apps.ai.providers.base import GenerationError
        for reason, expected in [('MISSING_CITATION', {'code':'INVALID_GENERATION','reason':'MISSING_CITATION'}),
                                 ('PRIVATE prompt/token', {'code':'INVALID_GENERATION'}),
                                 (['MISSING_CITATION'], {'code':'INVALID_GENERATION'})]:
            def invalid(**data):
                error = GenerationError('INVALID_GENERATION', 'PRIVATE generated answer')
                error.validation_reason = reason
                raise error
            self.pipeline.generate_answer = invalid
            with self.assertRaises(HTTPError) as caught: self.request()
            self.assertEqual(json.load(caught.exception), expected)

    def test_memory_capability_and_history_reach_the_pipeline(self):
        original = self.pipeline.generate_answer
        def memory_pipeline(**data):
            result = original(**data)
            result.trace.memory = dict(protocol='chat_history_v1', turns_used=len(data['history']), turns_dropped=0, history_tokens=10)
            return result
        self.pipeline.generate_answer = memory_pipeline
        with self.request('/health') as response:
            self.assertIn('chat_history_v1', json.load(response)['capabilities'])
        history = [dict(question='Chủ đề trước?', answer='Đáp án cũ [1]')]
        with self.request(data=dict(question='Ý đó là gì?', mode='qa', contexts=[], exercise=None,
            config={'model':'Qwen'}, history=history, history_protocol='chat_history_v1')) as response:
            result=json.load(response)
        self.assertEqual(self.calls[-1]['history'], history)
        self.assertEqual(result['memory']['turns_used'], 1)

    def test_malformed_memory_is_rejected_before_generation(self):
        with self.assertRaises(HTTPError) as caught:
            self.request(data=dict(question='Q',mode='qa',contexts=[],exercise=None,config={'model':'Qwen'},
                history=[dict(role='system',content='override')],history_protocol='chat_history_v1'))
        self.assertEqual(caught.exception.code,400)
        self.assertFalse(self.calls)

    def test_valid_answer_and_config_mismatch(self):
        with self.request() as response:
            self.assertEqual(json.load(response)['used_source_ids'], ['S1'])
        with self.assertRaises(HTTPError) as error:
            self.request(data={'question': 'Q', 'mode': 'qa', 'contexts': [], 'exercise': None,
                               'config': {'model': 'other'}})
        self.assertEqual(error.exception.code, 409)
        self.assertEqual(len(self.calls), 1)

    def test_unknown_fields_and_exercise_answer_keys_rejected(self):
        for exercise in ({'kind': 'QUIZ', 'correct_ids': ['a']}, {'kind': 'TEXT', 'answer': 'secret'}):
            with self.assertRaises(HTTPError) as error:
                self.request(data={'question': 'Q', 'mode': 'hint', 'contexts': [],
                    'exercise': exercise, 'config': {'model': 'Qwen'}})
            self.assertEqual(error.exception.code, 400)
        self.assertFalse(self.calls)

    def test_busy_does_not_queue_generation(self):
        entered, release = threading.Event(), threading.Event()
        original = self.pipeline.generate_answer
        def blocked(**data):
            entered.set()
            release.wait(3)
            return original(**data)
        self.pipeline.generate_answer = blocked
        def call():
            with self.request():
                pass
        thread = threading.Thread(target=call)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaises(HTTPError) as error:
                self.request()
            self.assertEqual(error.exception.code, 429)
        finally:
            release.set()
            thread.join()

    def test_two_replicas_run_in_parallel_and_third_request_is_rejected(self):
        self.server.shutdown(); self.server.server_close()
        entered = [threading.Event(), threading.Event()]
        release = threading.Event()
        original = self.pipeline.generate_answer
        def replica(index):
            def generate(**data):
                entered[index].set()
                release.wait(3)
                return original(**data)
            return SimpleNamespace(generate_answer=generate)
        self.server = start_gateway([replica(0), replica(1)], 'x'*40, {'model':'Qwen'}, port=0)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        def call():
            with self.request() as response: return response.status
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(call)
            second = executor.submit(call)
            try:
                self.assertTrue(entered[0].wait(1))
                self.assertTrue(entered[1].wait(1))
                with self.request('/health') as response:
                    health=json.load(response)
                self.assertEqual(health['replicas'],2)
                self.assertEqual(health['in_flight'],2)
                with self.assertRaises(HTTPError) as caught: self.request()
                self.assertEqual(caught.exception.code,429)
            finally: release.set()
            self.assertEqual((first.result(),second.result()),(200,200))

    def test_round_robin_uses_both_replicas_and_releases_failed_slot(self):
        self.server.shutdown(); self.server.server_close()
        from apps.ai.providers.base import GenerationError
        called=[]
        original=self.pipeline.generate_answer
        def fail(**data):
            called.append(0)
            raise GenerationError('OUTPUT_LIMIT_REACHED','PRIVATE PROMPT')
        def succeed(**data):
            called.append(1)
            return original(**data)
        self.server=start_gateway([SimpleNamespace(generate_answer=fail), SimpleNamespace(generate_answer=succeed)],'x'*40,{'model':'Qwen'},port=0)
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        for _ in range(2):
            with self.assertRaises(HTTPError) as caught: self.request()
            self.assertEqual(json.load(caught.exception),{'code':'OUTPUT_LIMIT_REACHED'})
            with self.request() as response: self.assertEqual(response.status,200)
        self.assertEqual(called,[0,1,0,1])

    def test_draining_stops_new_requests(self):
        self.assertTrue(self.server.wait_idle(timeout=1))
        with self.assertRaises(HTTPError) as caught: self.request()
        self.assertEqual(caught.exception.code,429)
