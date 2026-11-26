from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import threading
from unittest.mock import Mock, MagicMock, patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, transaction, DatabaseError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ai.models import GenerationEvent, GenerationGate
from apps.ai.operations import admit, claim, generation_slot, gateway_health, operations_snapshot
from apps.documents.exceptions import DocumentError
from tests.ai.test_w4_service import ChatServiceTests


class AdmissionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('admission-student', role='STUDENT')

    def finish(self, mode='qa'):
        with generation_slot(self.user, mode) as call:
            return call(lambda: {'usage': {'input_tokens': 12, 'output_tokens': 4}})

    def test_twenty_per_rolling_hour_then_reject_before_call(self):
        for _ in range(20):
            self.finish()
        generate = Mock()
        with self.assertRaises(DocumentError) as caught:
            with generation_slot(self.user, 'qa') as call:
                call(generate)
        self.assertEqual((caught.exception.code, caught.exception.status), ('AI_QUOTA_EXCEEDED', 429))
        generate.assert_not_called()
        self.assertEqual(GenerationEvent.objects.filter(gateway_calls=1).count(), 20)
        rejected = GenerationEvent.objects.get(status='REJECTED')
        self.assertEqual(rejected.gateway_calls, 0)
        GenerationEvent.objects.exclude(pk=rejected.pk).update(created_at=timezone.now()-timedelta(hours=1, seconds=1))
        self.finish()

    def test_one_running_five_waiting_and_sixth_waiter_rejected(self):
        first = admit(self.user, 'qa')
        waiting = [admit(self.user, 'hint') for _ in range(5)]
        self.assertEqual(first.status, 'RUNNING')
        self.assertTrue(all(item.status == 'QUEUED' for item in waiting))
        with self.assertRaises(DocumentError) as caught:
            admit(self.user, 'qa')
        self.assertEqual(caught.exception.code, 'AI_QUEUE_FULL')
        self.assertEqual(GenerationEvent.objects.filter(status='QUEUED').count(), 5)
        self.assertFalse(claim(waiting[1]))
        GenerationEvent.objects.filter(pk=first.pk).update(status='COMPLETED')
        self.assertFalse(claim(waiting[1]))
        self.assertTrue(claim(waiting[0]))

    def test_expired_workers_and_waiters_do_not_keep_slots_forever(self):
        active = admit(self.user, 'qa')
        queued = admit(self.user, 'qa')
        GenerationEvent.objects.filter(pk__in=[active.pk, queued.pk]).update(expires_at=timezone.now()-timedelta(seconds=1))
        next_event = admit(self.user, 'qa')
        self.assertEqual(next_event.status, 'RUNNING')
        self.assertEqual(GenerationEvent.objects.get(pk=active.pk).code, 'GENERATION_TIMEOUT')
        self.assertEqual(GenerationEvent.objects.get(pk=queued.pk).code, 'AI_QUEUE_TIMEOUT')

    @override_settings(AI_QUEUE_SECONDS=1)
    def test_queue_timeout_never_calls_generator_and_releases_waiter(self):
        admit(self.user, 'qa')
        generate = Mock()
        with patch('apps.ai.operations.monotonic', side_effect=[0, 2]):
            with self.assertRaises(DocumentError) as caught:
                with generation_slot(self.user, 'qa') as call:
                    call(generate)
        self.assertEqual(caught.exception.code, 'AI_QUEUE_TIMEOUT')
        generate.assert_not_called()
        self.assertFalse(GenerationEvent.objects.filter(status='QUEUED').exists())

    def test_failure_releases_slot_and_never_persists_exception_or_content(self):
        private = 'PRIVATE_PROMPT SECRET_TOKEN ANSWER_TEXT'
        with self.assertRaises(RuntimeError):
            with generation_slot(self.user, 'summary') as call:
                call(Mock(side_effect=RuntimeError(private)))
        event = GenerationEvent.objects.get()
        self.assertEqual(event.code, 'GENERATION_UNAVAILABLE')
        self.assertEqual(event.status, 'FAILED')
        self.assertNotIn(private, str(event.__dict__))
        self.finish()

    def test_one_slot_cannot_send_two_gateway_calls(self):
        with self.assertRaises(DocumentError):
            with generation_slot(self.user, 'qa') as call:
                call(lambda: {})
                call(lambda: {})
        self.assertEqual(GenerationEvent.objects.get().gateway_calls, 1)

    @override_settings(AI_HOURLY_STUDENT=1)
    def test_student_quota_is_not_shared_between_accounts(self):
        self.finish()
        other = get_user_model().objects.create_user('admission-other', role='STUDENT')
        with generation_slot(other, 'hint') as call:
            call(lambda: {})
        self.assertEqual(GenerationEvent.objects.filter(status='COMPLETED').count(), 2)

    @override_settings(AI_CONCURRENT=0)
    def test_invalid_operational_config_fails_closed(self):
        with self.assertRaises(DocumentError):
            admit(self.user, 'qa')
        self.assertEqual(GenerationEvent.objects.count(), 0)

    def test_health_counters_are_aggregate_and_no_source_or_user_data(self):
        self.finish()
        with patch('apps.ai.operations.gateway_health', return_value={'status':'UNAVAILABLE'}):
            snapshot = operations_snapshot()
        self.assertEqual(snapshot['generation']['gateway_calls'], 1)
        self.assertEqual(snapshot['generation']['input_tokens'], 12)
        self.assertEqual(snapshot['generation']['output_tokens'], 4)
        self.assertNotIn(self.user.username, json.dumps(snapshot))
        client = APIClient()
        with transaction.atomic():
            self.assertEqual(client.get('/api/ai/operations/').status_code, 401)
        client.force_authenticate(self.user)
        self.assertEqual(client.get('/api/ai/operations/').status_code, 403)
        self.user.role = 'ADMIN'
        self.user.save(update_fields=['role'])
        with patch('apps.ai.operations.gateway_health', return_value={'status':'UNAVAILABLE'}):
            response = client.get('/api/ai/operations/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])

    def test_gateway_health_checks_real_transport_boundary_and_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.json'
            path.write_text(json.dumps({'model':'Qwen'}), encoding='utf-8')
            with override_settings(AI_GENERATION_CONFIG=str(path), AI_INFERENCE_URL='https://example.test', AI_INFERENCE_TOKEN='x'*40):
                opener = MagicMock()
                response = opener.open.return_value.__enter__.return_value
                response.read.return_value = json.dumps(dict(ready=True, replicas=2, in_flight=0,
                    config={'model':'Qwen'}, private_prompt='PRIVATE_CONTENT')).encode()
                with patch('apps.ai.remote.build_opener', return_value=opener):
                    result = gateway_health()
                self.assertEqual(result, dict(status='READY', replicas=2, in_flight=0))
                self.assertEqual(opener.open.call_args.kwargs['timeout'], 3)
                response.read.return_value = b'{"config":{"model":"wrong"}}'
                with patch('apps.ai.remote.build_opener', return_value=opener):
                    self.assertEqual(gateway_health()['code'], 'GENERATION_CONFIG_MISMATCH')
                opener.open.side_effect = RuntimeError('PRIVATE_TOKEN')
                with patch('apps.ai.remote.build_opener', return_value=opener):
                    self.assertEqual(gateway_health(),dict(status='UNAVAILABLE',code='GENERATION_UNAVAILABLE'))

    def test_unavailable_metrics_database_is_not_reported_as_zero_or_leaked(self):
        self.user.role = 'ADMIN'
        self.user.save(update_fields=['role'])
        client = APIClient()
        client.force_authenticate(self.user)
        with patch('apps.ai.operations.operations_snapshot', side_effect=DatabaseError('PRIVATE SQL CONNECTION')):
            response = client.get('/api/ai/operations/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['code'], 'GENERATION_UNAVAILABLE')
        self.assertNotIn('PRIVATE', str(response.data))


class DocumentReadQuotaTests(TestCase):
    from tests.documents import test_material_access as material
    setUp = material.MaterialAccessTests.setUp
    login = material.MaterialAccessTests.login
    upload = material.MaterialAccessTests.upload
    upload_file = material.MaterialAccessTests.upload_file
    prepare = material.MaterialAccessTests.prepare
    publish = material.MaterialAccessTests.publish

    def test_protected_pdf_remains_readable_after_twenty_ai_requests(self):
        self.prepare()
        self.assertEqual(self.publish().status_code, 200)
        self.login('student', 'Student123!')
        for _ in range(20):
            with generation_slot(self.student, 'qa') as call:
                call(lambda: {})
        with self.assertRaises(DocumentError) as caught:
            admit(self.student, 'qa')
        self.assertEqual(caught.exception.code, 'AI_QUOTA_EXCEEDED')
        response = self.client.get(self.base+'view/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/pdf', response['Content-Type'])


class OperationalServiceTests(ChatServiceTests):
    @override_settings(AI_HOURLY_STUDENT=1)
    def test_quota_blocks_model_but_does_not_block_course_reading(self):
        self.call()
        with self.assertRaises(DocumentError) as caught:
            self.call()
        self.assertEqual(caught.exception.code, 'AI_QUOTA_EXCEEDED')
        self.assertEqual(self.runtime.generate.call_count, 1)
        client = APIClient()
        client.force_authenticate(self.student)
        self.assertEqual(client.get('/api/health/').status_code, 200)
        self.assertEqual(client.get(f'/api/courses/{self.course.pk}/').status_code, 200)

    def test_empty_source_does_not_consume_quota_or_call_model(self):
        self.data['document_ids'] = []
        self.call()
        self.assertFalse(GenerationEvent.objects.exists())

    def test_policy_rechecked_after_waiting_before_model(self):
        from apps.ai.services import enforce_chat_policy
        original = enforce_chat_policy
        calls = []
        def recheck(user, data):
            calls.append(True)
            if len(calls) == 3:
                raise DocumentError('AI_NOT_ALLOWED', 'Private provider details', 403)
            return original(user, data)
        with patch('apps.ai.services.enforce_chat_policy', side_effect=recheck):
            with self.assertRaises(DocumentError) as caught:
                self.call()
        self.assertEqual(caught.exception.code, 'AI_NOT_ALLOWED')
        self.runtime.generate.assert_not_called()
        self.assertEqual(GenerationEvent.objects.get().gateway_calls, 0)


class ConcurrentAdmissionTests(TransactionTestCase):
    def test_waiting_http_worker_runs_after_first_worker_releases_its_slot(self):
        user = get_user_model().objects.create_user('waiting-student', role='STUDENT')
        GenerationGate.objects.create(pk=1)
        entered, release = threading.Event(), threading.Event()
        lock = threading.Lock()
        active = 0
        peak = 0
        def worker(block):
            nonlocal active, peak
            close_old_connections()
            try:
                actual = get_user_model().objects.get(pk=user.pk)
                def generate():
                    nonlocal active, peak
                    with lock:
                        active += 1
                        peak = max(peak, active)
                    try:
                        if block:
                            entered.set()
                            if not release.wait(5):
                                raise TimeoutError('test worker timeout')
                        return {}
                    finally:
                        with lock:
                            active -= 1
                with generation_slot(actual, 'qa') as call:
                    return call(generate)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(worker, True)
            try:
                self.assertTrue(entered.wait(3))
                second = pool.submit(worker, False)
                from time import monotonic, sleep
                deadline = monotonic()+3
                while not GenerationEvent.objects.filter(status='QUEUED').exists() and monotonic()<deadline:
                    sleep(0.02)
                self.assertTrue(GenerationEvent.objects.filter(status='QUEUED').exists())
            finally:
                release.set()
            self.assertEqual(first.result(timeout=5), {})
            self.assertEqual(second.result(timeout=5), {})
        self.assertEqual(peak, 1)
        self.assertEqual(GenerationEvent.objects.filter(status='COMPLETED', gateway_calls=1).count(), 2)

    def test_workers_share_one_slot_and_bounded_fifo_queue(self):
        user = get_user_model().objects.create_user('concurrent-student', role='STUDENT')
        GenerationGate.objects.create(pk=1)
        def worker(_):
            close_old_connections()
            try:
                actual = get_user_model().objects.get(pk=user.pk)
                try:
                    return admit(actual, 'qa').status
                except DocumentError as exc:
                    return exc.code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(8)))
        self.assertEqual(results.count('RUNNING'), 1)
        self.assertEqual(results.count('QUEUED'), 5)
        self.assertEqual(results.count('AI_QUEUE_FULL'), 2)
