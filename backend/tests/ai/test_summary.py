from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.utils import timezone
from rest_framework.test import APIClient
from apps.ai.api.serializers import ChatRequest
from apps.ai.models import SummaryTask
from apps.ai.services import answer_chat
from apps.ai.summary import advance_summary, owned_task, separate_source_footers, compact_note_blocks
from apps.documents.exceptions import DocumentError
from apps.documents.retrieval_contracts import Chunk
from apps.courses.assessment_models import Assessment, AssessmentAttempt
from tests.documents.test_retrieval_scope import ScopeFixture


class SummaryTests(ScopeFixture):
    def test_only_redundant_trailing_known_source_footer_is_separated(self):
        paragraphs=[dict(text='Nội dung tổng hợp. Các nguồn tham khảo: S.1, S.2.',sources=['S1','S2'])]
        normalized,changes=separate_source_footers(paragraphs)
        self.assertEqual(normalized,[dict(text='Nội dung tổng hợp.',sources=['S1','S2'])])
        self.assertEqual(changes,[dict(paragraph=0,removed_footer='Các nguồn tham khảo: S.1, S.2.')])
        self.assertIn('S.1',paragraphs[0]['text'])
        for text in ('Tên tài liệu S.1 có ý nghĩa riêng.', 'Các nguồn tham khảo: giáo trình.'):
            values=[dict(text=text,sources=['S1'])]
            self.assertEqual(separate_source_footers(values),(values,[]))

    def test_footer_cannot_hide_unknown_sources_or_replace_empty_prose(self):
        for text in ('Nội dung. Các nguồn tham khảo: S.99.', 'Các nguồn tham khảo: S.1.'):
            with self.assertRaises(DocumentError):
                separate_source_footers([dict(text=text,sources=['S1'])])

    def test_compact_note_blocks_preserve_all_text_without_truncation(self):
        notes=[dict(paragraphs=[dict(text='Tri thức và niềm tin. '*100,sources=['S1','S2']),
                                dict(text='Phương pháp luận.',sources=['S2'])])]
        blocks=compact_note_blocks(notes)
        self.assertTrue(all(0<len(row['text'])<=700 for row in blocks))
        self.assertEqual(''.join(row['text'] for row in blocks),
            ''.join(p['text'] for note in notes for p in note['paragraphs']))
        self.assertEqual([b['id'] for b in blocks],[f'B{i}' for i in range(1,len(blocks)+1)])

    def prepare_final_notes(self):
        task=SummaryTask.objects.get(pk=self.create()['id'])
        task.state.update(synthesis_strategy='legacy_reduce',cursor=len(task.state['blocks']),notes=[
            dict(paragraphs=[dict(text='Ý thứ nhất. '*30,sources=['S1'])]),
            dict(paragraphs=[dict(text='Ý thứ hai. '*30,sources=['S2'])])],next_notes=[],steps=3)
        task.save()
        return task

    def test_large_final_notes_use_shorter_synthesis_only_when_every_block_fits(self):
        task=self.prepare_final_notes()
        def generate(**kwargs):
            source=kwargs['records'][0]['source_id']
            return dict(protocol='coherent_summary_v1',phase=kwargs['phase'],consumed=len(kwargs['records']),
                input_tokens=100,paragraphs=[dict(text='Chủ đề đầu.' if source=='S1' else 'Chủ đề cuối.',sources=[source])])
        self.runtime.summarize.side_effect=generate
        with patch('apps.ai.summary.COMPACT_FINAL_CHARACTERS',1):
            result=advance_summary(self.student,task.pk,self.runtime)
            self.assertEqual(result['status'],'PENDING')
            self.assertIsNone(result['result'])
            result=advance_summary(self.student,task.pk,self.runtime)
        self.assertEqual(result['status'],'COMPLETED')
        call=self.runtime.summarize.call_args.kwargs
        self.assertEqual(call['phase'],'map')
        self.assertEqual(result['result']['coverage']['final_synthesis']['input_blocks'],2*len(call['records']))
        self.assertEqual(result['result']['coverage']['final_synthesis']['sections_completed'],2)
        self.assertEqual(result['result']['coverage']['final_synthesis']['strategy'],'topic_sections')
        self.assertEqual(result['result']['coverage']['final_synthesis']['output_budget_tokens'],640)
        self.assertEqual(len(result['result']['citations']),3)
        self.assertEqual(result['result']['answer'],'Chủ đề đầu.\n\nChủ đề cuối.')

    def test_section_failure_cannot_publish_the_first_section_as_complete(self):
        task=self.prepare_final_notes()
        def generate(**kwargs):
            first=kwargs['records'][0]['source_id']=='S1'
            return dict(protocol='coherent_summary_v1',phase='map',consumed=len(kwargs['records']),input_tokens=100,
                paragraphs=[dict(text='Chủ đề đầu.',sources=['S1'])] if first else [])
        self.runtime.summarize.side_effect=generate
        with patch('apps.ai.summary.COMPACT_FINAL_CHARACTERS',1):
            self.assertEqual(advance_summary(self.student,task.pk,self.runtime)['status'],'PENDING')
            result=advance_summary(self.student,task.pk,self.runtime)
        self.assertEqual(result['status'],'FAILED')
        self.assertIsNone(result['result'])
        task.refresh_from_db()
        self.assertEqual(len(task.state['final_sections']),1)

    def test_partial_compact_synthesis_is_never_published(self):
        task=self.prepare_final_notes()
        task.state['notes'][0]['paragraphs'][0]['text']='Ý thứ nhất. '*100
        task.save()
        self.runtime.summarize.side_effect=lambda **kwargs: dict(protocol='coherent_summary_v1',phase='map',
            consumed=1,input_tokens=100,paragraphs=[dict(text='Chưa đọc đủ.',sources=['S1'])])
        with patch('apps.ai.summary.COMPACT_FINAL_CHARACTERS',1):
            result=advance_summary(self.student,task.pk,self.runtime)
        self.assertEqual(result['status'],'FAILED')
        self.assertIsNone(result['result'])
        task.refresh_from_db()
        self.assertEqual(task.state['steps'],3)
        self.assertEqual(len(task.state['notes']),2)

    def setUp(self):
        super().setUp()
        self.version.page_count = 3
        self.version.save(update_fields=['page_count'])
        self.data = dict(mode='summary', question='Tóm tắt', course_id=str(self.course.pk),
            document_ids=[str(self.doc.pk)], summary_request_id=uuid4())
        self.chunks = [Chunk('1.0', f'chunk-{p}', str(self.course.pk), str(self.doc.pk), str(self.version.pk),
            'Triết học', p, None, 0, f'Triết học nghiên cứu thế giới và con người; đây là nội dung của trang {p}.',
            30, 0, 90, self.version.checksum_sha256, 'b'*64) for p in range(1, 4)]
        def generate(*, phase, records, config):
            sources = [records[0]['source_id']] if phase == 'map' else records[0]['paragraphs'][0]['sources']
            return dict(protocol='coherent_summary_v1', phase=phase, consumed=1 if phase == 'map' else len(records),
                input_tokens=100, paragraphs=[dict(text='Triết học tìm hiểu thế giới và vị trí của con người.', sources=sources)])
        self.runtime = SimpleNamespace(catalog={c.chunk_id:c for c in self.chunks}, config={'max_input_tokens':3584},
            generate=Mock(), summarize=Mock(side_effect=generate))

    def create(self):
        return answer_chat(user=self.student, data=self.data, request_id=str(uuid4()), runtime=self.runtime)

    def finish(self, task_id):
        for _ in range(20):
            result = advance_summary(self.student, task_id, self.runtime)
            if result['status'] in ('COMPLETED', 'FAILED'):
                return result
        self.fail('Summary did not finish')

    def test_reads_every_source_block_before_publishing_without_rewriting_generated_claims(self):
        task = self.create()
        self.assertEqual(task['status'], 'PENDING')
        self.assertIsNone(task['result'])
        first = advance_summary(self.student, task['id'], self.runtime)
        self.assertIsNone(first['result'])
        result = self.finish(task['id'])
        self.assertEqual(result['status'], 'COMPLETED')
        coverage = result['result']['coverage']
        self.assertEqual(coverage['pages_scanned'], [1, 2, 3])
        self.assertEqual(coverage['chunks_scanned'], 3)
        self.assertEqual(coverage['blocks_read'], coverage['blocks_total'])
        self.assertEqual(coverage['citation_scope'], 'input_range')
        self.assertEqual(len(result['result']['citations']), 3)
        self.assertNotIn('[1]', result['result']['answer'])
        self.assertTrue(all(call.kwargs['phase'] == 'map' for call in self.runtime.summarize.call_args_list))
        self.assertEqual(coverage['final_synthesis']['strategy'],'source_sections_v1')
        self.assertFalse(coverage['final_synthesis']['generated_notes_rewritten'])
        self.runtime.generate.assert_not_called()

    def test_source_sections_retain_early_and_late_topics_verbatim_from_model(self):
        def generate(**kwargs):
            source=kwargs['records'][0]['source_id']
            return dict(protocol='coherent_summary_v1',phase='map',consumed=1,input_tokens=100,
                paragraphs=[dict(text=f'Chủ đề {source[-1]}.',sources=[source])])
        self.runtime.summarize.side_effect=generate
        result=self.finish(self.create()['id'])
        self.assertEqual(result['result']['answer'],'Chủ đề 1.\n\nChủ đề 2.\n\nChủ đề 3.')
        task=SummaryTask.objects.get(pk=result['id'])
        self.assertEqual(len(task.state['source_sections']),3)
        self.assertEqual(task.state['steps'],3)

    def test_source_sections_never_publish_a_successful_prefix_after_late_failure(self):
        task=self.create()
        advance_summary(self.student,task['id'],self.runtime)
        self.runtime.summarize.side_effect=DocumentError('SUMMARY_GENERATION_FAILED','Failed source step',503)
        result=advance_summary(self.student,task['id'],self.runtime)
        self.assertEqual(result['status'],'FAILED')
        self.assertIsNone(result['result'])
        self.assertEqual(result['progress']['blocks_read'],1)

    def test_incomplete_source_sentence_retries_a_smaller_batch_without_advancing(self):
        self.runtime.catalog['chunk-1']=replace(self.chunks[0],text='Nội dung nguồn. '*600)
        task=self.create()
        attempts=[]
        def generate(**kwargs):
            attempts.append(kwargs['records'])
            return dict(protocol='coherent_summary_v1',phase='map',consumed=len(kwargs['records']),input_tokens=100,
                paragraphs=[dict(text='Thừa nhận cả cái ' if len(attempts)==1 else 'Nội dung được tổng hợp đầy đủ.',
                    sources=[kwargs['records'][0]['source_id']])])
        self.runtime.summarize.side_effect=generate
        first=advance_summary(self.student,task['id'],self.runtime)
        self.assertEqual(first['status'],'PENDING')
        self.assertEqual(first['progress']['blocks_read'],0)
        self.assertIsNone(first['result'])
        result=self.finish(task['id'])
        self.assertEqual(result['status'],'COMPLETED')
        self.assertEqual(len(attempts[0]),8)
        self.assertEqual(len(attempts[1]),4)
        self.assertEqual(result['result']['coverage']['format_retries'],1)
        self.assertEqual(result['result']['coverage']['generation_attempts'],len(attempts))
        expected=SummaryTask.objects.get(pk=task['id']).state['blocks']
        self.assertEqual([r['id'] for batch in attempts[1:] for r in batch],[r['id'] for r in expected])

    def test_incomplete_sentence_retry_is_bounded_and_never_published(self):
        self.runtime.summarize.side_effect=lambda **kwargs: dict(protocol='coherent_summary_v1',phase='map',
            consumed=1,input_tokens=100,paragraphs=[dict(text='Câu chưa hoàn tất và',sources=['S1'])])
        task=self.create()
        self.assertEqual(advance_summary(self.student,task['id'],self.runtime)['status'],'PENDING')
        result=advance_summary(self.student,task['id'],self.runtime)
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['error']['reason'],'SUMMARY_INCOMPLETE_SENTENCE')
        self.assertIsNone(result['result'])
        self.assertEqual(self.runtime.summarize.call_count,2)

    def test_partition_preserves_every_character_without_top_k(self):
        self.runtime.catalog['chunk-1'] = replace(self.chunks[0], text='Nội dung nguồn nguyên bản. '*100)
        task = owned_task(self.student, self.create()['id'])
        blocks = [b for b in task.state['blocks'] if b['source_id']=='S1']
        self.assertTrue(all(len(b['text']) <= 700 for b in blocks))
        self.assertEqual(''.join(b['text'] for b in blocks), self.runtime.catalog['chunk-1'].text)

    def test_map_batches_are_bounded_without_skipping_remaining_text(self):
        self.runtime.catalog['chunk-1'] = replace(self.chunks[0], text='Nội dung học liệu. '*500)
        original = self.runtime.summarize.side_effect
        def consume_batch(**kwargs):
            result = original(**kwargs)
            result['consumed'] = len(kwargs['records'])
            return result
        self.runtime.summarize.side_effect = consume_batch
        result = self.finish(self.create()['id'])
        self.assertEqual(result['status'], 'COMPLETED')
        maps = [call.kwargs['records'] for call in self.runtime.summarize.call_args_list if call.kwargs['phase'] == 'map']
        self.assertGreater(len(maps), 1)
        self.assertTrue(all(len(batch) <= 8 for batch in maps))
        self.assertEqual([block['id'] for batch in maps for block in batch],
            [block['id'] for block in SummaryTask.objects.get(pk=result['id']).state['blocks']])

    def test_selected_pages_do_not_read_other_pages(self):
        self.data.update(page_start=2, page_end=2)
        result = self.finish(self.create()['id'])['result']
        self.assertEqual(result['coverage']['pages_scanned'], [2])
        self.assertFalse(result['coverage']['whole_document'])
        self.assertEqual(result['citations'][0]['page_number'], 2)

    def test_missing_page_is_not_claimed_complete(self):
        del self.runtime.catalog['chunk-2']
        with self.assertRaises(DocumentError) as error:
            self.create()
        self.assertEqual(error.exception.code, 'SUMMARY_SOURCE_INCOMPLETE')

    def test_bad_provenance_and_bounds_are_rejected(self):
        self.runtime.catalog['chunk-1'] = replace(self.chunks[0], source_checksum='c'*64)
        with self.assertRaises(DocumentError): self.create()
        self.runtime.catalog['chunk-1'] = self.chunks[0]
        for bounds in [dict(page_start=3,page_end=2),dict(page_end=4)]:
            self.data.update(bounds)
            with self.assertRaises(DocumentError): self.create()

    def test_create_is_idempotent_but_conflicting_scope_is_not(self):
        first, second = self.create(), self.create()
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(SummaryTask.objects.count(), 1)
        self.data.update(page_start=2)
        with self.assertRaises(DocumentError): self.create()

    def test_completed_step_replay_does_not_generate_again(self):
        task_id = self.create()['id']
        result = self.finish(task_id)
        count = self.runtime.summarize.call_count
        self.assertEqual(advance_summary(self.student, task_id, self.runtime), result)
        self.assertEqual(self.runtime.summarize.call_count, count)

    def test_legacy_source_layout_is_rendered_without_rewriting_raw_result(self):
        task_id = self.create()['id']
        self.finish(task_id)
        task = SummaryTask.objects.get(pk=task_id)
        task.result['coverage'].pop('citation_scope')
        task.result['answer'] += ' [1]'
        task.save(update_fields=['result'])
        from apps.ai.summary import descriptor
        current = descriptor(owned_task(self.student, task_id))['result']
        self.assertNotIn('[1]', current['answer'])
        self.assertEqual(current['timing'], task.result['timing'])
        task.refresh_from_db()
        self.assertIn('[1]', task.result['answer'])

    def test_active_lease_does_not_start_duplicate_generation(self):
        task_id = self.create()['id']
        SummaryTask.objects.filter(pk=task_id).update(status='PROCESSING', lease_token=uuid4(), lease_expires_at=timezone.now()+timedelta(seconds=60))
        self.assertEqual(advance_summary(self.student, task_id, self.runtime)['status'], 'PROCESSING')
        self.runtime.summarize.assert_not_called()

    def test_busy_keeps_progress_and_can_resume(self):
        task_id = self.create()['id']
        original = self.runtime.summarize.side_effect
        self.runtime.summarize.side_effect = DocumentError('GENERATION_BUSY','Busy',429)
        result = advance_summary(self.student, task_id, self.runtime)
        self.assertEqual(result['status'], 'PENDING')
        self.assertEqual(result['progress']['blocks_read'], 0)
        self.runtime.summarize.side_effect = original
        self.assertEqual(self.finish(task_id)['status'], 'COMPLETED')

    def test_invalid_source_or_cursor_fails_without_partial_result(self):
        for change in [dict(consumed=999),dict(paragraphs=[dict(text='Invented',sources=['S999'])])]:
            self.data['summary_request_id'] = uuid4()
            task_id = self.create()['id']
            self.runtime.summarize.side_effect = None
            self.runtime.summarize.return_value = dict(protocol='coherent_summary_v1',phase='map',consumed=1,input_tokens=100,
                paragraphs=[dict(text='Nội dung.',sources=['S1'])],**{}) | change
            result = advance_summary(self.student, task_id, self.runtime)
            self.assertEqual(result['status'], 'FAILED')
            self.assertIsNone(result['result'])

    def test_revocation_during_generation_prevents_delivery(self):
        task_id = self.create()['id']
        original = self.runtime.summarize.side_effect
        def revoke(**kwargs):
            self.doc.is_published=False; self.doc.save()
            return original(**kwargs)
        self.runtime.summarize.side_effect = revoke
        with self.assertRaises(DocumentError): advance_summary(self.student, task_id, self.runtime)

    def test_wrong_owner_and_changed_version_cannot_read_result(self):
        task_id = self.create()['id']
        with self.assertRaises(DocumentError): owned_task(self.owner, task_id)
        self.doc.is_published=False; self.doc.save()
        with self.assertRaises(DocumentError): owned_task(self.student, task_id)

    def test_failed_gateway_does_not_fall_back_to_extractive_summary(self):
        task_id = self.create()['id']
        self.runtime.summarize.side_effect = DocumentError('GENERATION_CONFIG_MISMATCH','Old gateway',503)
        result = advance_summary(self.student, task_id, self.runtime)
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['error']['code'], 'GENERATION_CONFIG_MISMATCH')
        self.assertIsNone(result['result'])

    def test_failure_exposes_only_allowlisted_diagnostic_codes(self):
        failure=DocumentError('SUMMARY_GENERATION_FAILED','PRIVATE text',503)
        failure.remote_code='INVALID_GENERATION'
        failure.validation_reason='SUMMARY_EMBEDDED_CITATION'
        self.runtime.summarize.side_effect=failure
        result=advance_summary(self.student,self.create()['id'],self.runtime)
        self.assertEqual(result['error'],dict(code='SUMMARY_GENERATION_FAILED',remote_code='INVALID_GENERATION',
            reason='SUMMARY_EMBEDDED_CITATION'))
        self.assertNotIn('PRIVATE',str(result))

    def test_transport_preserves_safe_failure_details_without_raw_output(self):
        import io
        import json
        from urllib.error import HTTPError
        from apps.ai.remote import summarize_step
        body=json.dumps(dict(code='INVALID_GENERATION',reason='SUMMARY_UNKNOWN_SOURCE',answer='PRIVATE text')).encode()
        error=HTTPError('https://example.test/summary',503,'Error',{},io.BytesIO(body))
        with patch.dict('os.environ',{'AI_INFERENCE_URL':'https://example.test','AI_INFERENCE_TOKEN':'x'*40}), \
                patch('apps.ai.remote.build_opener') as opener:
            opener.return_value.open.side_effect=error
            with self.assertRaises(DocumentError) as caught:
                summarize_step(phase='map',records=[],config={'timeout_seconds':90})
        self.assertEqual(caught.exception.remote_code,'INVALID_GENERATION')
        self.assertEqual(caught.exception.validation_reason,'SUMMARY_UNKNOWN_SOURCE')
        self.assertNotIn('PRIVATE',caught.exception.message)

    def test_http_start_status_advance_and_no_client_notes(self):
        client=APIClient(); client.force_authenticate(self.student)
        with patch('apps.ai.summary.get_runtime',return_value=self.runtime):
            response=client.post('/api/ai/chat/',self.data,format='json')
            self.assertEqual(response.status_code,202,response.data)
            url=f"/api/ai/summaries/{response.data['id']}/"
            self.assertEqual(client.get(url).status_code,200)
            self.assertEqual(client.post(url,{'notes':'fake'},format='json').status_code,400)
            self.assertIn(client.post(url,{},format='json').status_code,(200,202))

    def test_serializer_rejects_history_and_ambiguous_scope(self):
        for changes in [dict(document_ids=[]),dict(document_ids=[str(self.doc.pk),str(uuid4())]),
                        dict(conversation_id=uuid4(),client_message_id=uuid4()), dict(mode='qa',summary_request_id=uuid4())]:
            self.assertFalse(ChatRequest(data={**self.data,**changes}).is_valid())

    def test_active_test_blocks_create_and_reading_existing_task(self):
        task_id=self.create()['id']
        exam=Assessment.objects.create(session=self.session,title='Kiểm tra',kind='TEXT',mode='TEST',is_published=True,due_at=timezone.now()+timedelta(hours=1))
        AssessmentAttempt.objects.create(assessment=exam,student=self.student,request_id=uuid4(),number=1,expires_at=exam.due_at)
        with self.assertRaises(DocumentError): owned_task(self.student,task_id)
        with self.assertRaises(DocumentError): self.create()

    def test_test_started_during_summary_blocks_publication_and_next_inference(self):
        task_id = self.create()['id']
        original = self.runtime.summarize.side_effect
        def start_test(**kwargs):
            exam = Assessment.objects.create(session=self.session, title='Kiểm tra', kind='TEXT',
                mode='TEST', is_published=True, due_at=timezone.now()+timedelta(hours=1))
            AssessmentAttempt.objects.create(assessment=exam, student=self.student, request_id=uuid4(),
                number=1, expires_at=exam.due_at)
            return original(**kwargs)
        self.runtime.summarize.side_effect = start_test
        with self.assertRaises(DocumentError) as caught:
            advance_summary(self.student, task_id, self.runtime)
        self.assertEqual(caught.exception.code, 'AI_NOT_ALLOWED')
        self.assertIsNone(SummaryTask.objects.get(pk=task_id).result)
        with self.assertRaises(DocumentError):
            advance_summary(self.student, task_id, self.runtime)
        self.runtime.summarize.assert_called_once()

    def test_timeout_never_publishes_partial_output_or_raw_provider_text(self):
        task_id = self.create()['id']
        failure = DocumentError('SUMMARY_GENERATION_FAILED', 'PRIVATE provider text', 503)
        failure.remote_code = 'GENERATION_TIMEOUT'
        self.runtime.summarize.side_effect = failure
        result = advance_summary(self.student, task_id, self.runtime)
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['error']['remote_code'], 'GENERATION_TIMEOUT')
        self.assertIsNone(result['result'])
        self.assertNotIn('PRIVATE', str(result))

    def test_expired_task_fails_without_inference(self):
        task_id=self.create()['id']
        SummaryTask.objects.filter(pk=task_id).update(created_at=timezone.now()-timedelta(hours=1))
        result=advance_summary(self.student,task_id,self.runtime)
        self.assertEqual(result['error']['code'],'SUMMARY_EXPIRED')
        self.runtime.summarize.assert_not_called()

    def test_odd_reduction_rounds_keep_all_notes(self):
        task_id=self.create()['id']
        task=SummaryTask.objects.get(pk=task_id)
        task.state.pop('synthesis_strategy')
        task.save()
        base=self.runtime.summarize.side_effect
        def pairs(**kwargs):
            result=base(**kwargs)
            if kwargs['phase']=='reduce': result['consumed']=2
            return result
        self.runtime.summarize.side_effect=pairs
        self.assertEqual(self.finish(task_id)['status'],'COMPLETED')
        self.assertTrue(any(call.kwargs['phase']=='reduce' for call in self.runtime.summarize.call_args_list))

    def test_configuration_cannot_change_mid_summary(self):
        task_id=self.create()['id']
        self.runtime.config={**self.runtime.config,'max_input_tokens':2000}
        result=advance_summary(self.student,task_id,self.runtime)
        self.assertEqual(result['error']['code'],'GENERATION_CONFIG_MISMATCH')
        self.runtime.summarize.assert_not_called()

    def test_catalog_identity_must_match_its_key(self):
        self.runtime.catalog['chunk-1']=replace(self.chunks[0],chunk_id='different')
        with self.assertRaises(DocumentError): self.create()
