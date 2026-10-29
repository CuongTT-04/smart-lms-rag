from copy import deepcopy
import hashlib
from itertools import product
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.instruction.common import InstructionError, digest, read_json, read_jsonl
from scripts.instruction.export_sft_dataset import connected_components, validate_plan
from scripts.instruction.prepare_sft import (collate, make_plan, prepare, tokenize_example, tokenizer_provenance)
from scripts.instruction.tests.support import production_resource, record, rehash, resources, reviews


class TestTokenizer:
    """Character tokenizer for isolated contract tests, never a real-model audit."""
    eos_token_id=2
    pad_token_id=0
    all_special_tokens=['<eos>','<assistant>']
    emit_eos=True
    suffix='\n'

    def __call__(self,text,**kwargs):
        ids=[];index=0
        while index<len(text):
            if self.emit_eos and text.startswith('<eos>',index):
                ids.append(self.eos_token_id);index+=5
            else:
                ids.append(ord(text[index])+10);index+=1
        return {'input_ids':ids}

    def decode(self,ids,**kwargs):
        return ''.join('<eos>' if token==self.eos_token_id else chr(token-10) for token in ids)

    def apply_chat_template(self,messages,*,tokenize,add_generation_prompt):
        text=''.join('<'+m['role']+'>\n'+m['content']+'<eos>'+self.suffix for m in messages)
        if add_generation_prompt:text+='<assistant>\n'
        return self(text)['input_ids'] if tokenize else text


class TokenAuditTests(unittest.TestCase):
    def sample(self):
        return {'prompt':[{'role':'system','content':'system'},{'role':'user','content':'source'}],
                'completion':[{'role':'assistant','content':'Answer [1].'}]}

    def test_prefix_content_eos_and_trailing_format_masks(self):
        tok=TestTokenizer();encoded,stats=tokenize_example(self.sample(),tok,resources().contract['format'])
        start=stats['prompt_tokens'];end=start+stats['supervised_target_tokens']
        self.assertEqual(encoded['labels'][:start],[-100]*start)
        self.assertEqual(encoded['labels'][start:end+1],encoded['input_ids'][start:end+1])
        self.assertEqual(encoded['labels'][end],tok.eos_token_id)
        self.assertEqual(encoded['labels'][end+1:],[-100])
        self.assertEqual(encoded['attention_mask'],[1]*len(encoded['input_ids']))

    def test_budget_failures_are_not_silently_truncated(self):
        for key,code in [('max_prompt_tokens','PROMPT_TOKEN_LIMIT'),
                         ('max_completion_tokens','COMPLETION_TOKEN_LIMIT'),
                         ('max_sequence_tokens','SEQUENCE_TOKEN_LIMIT')]:
            limits=deepcopy(resources().contract['format']);limits[key]=1
            with self.subTest(key=key),self.assertRaisesRegex(InstructionError,code):
                tokenize_example(self.sample(),TestTokenizer(),limits)

    def test_reserved_tokens_and_empty_targets_fail(self):
        for value,code in [('<eos>','RESERVED_TOKEN_IN_DATA'),('','INVALID_SFT_ROLES')]:
            sample=self.sample();sample['completion'][0]['content']=value
            with self.subTest(value=value),self.assertRaisesRegex(InstructionError,code):
                tokenize_example(sample,TestTokenizer(),resources().contract['format'])

    def test_missing_eos_and_nonformat_suffix_fail(self):
        tok=TestTokenizer();tok.emit_eos=False
        with self.assertRaisesRegex(InstructionError,'COMPLETION_EOS_COUNT'):
            tokenize_example(self.sample(),tok,resources().contract['format'])
        tok=TestTokenizer();tok.suffix='not whitespace'
        with self.assertRaisesRegex(InstructionError,'NON_FORMAT_TEXT_AFTER_EOS'):
            tokenize_example(self.sample(),tok,resources().contract['format'])

    def test_template_prefix_mismatch_fails(self):
        tok=TestTokenizer();original=tok.apply_chat_template
        def changed(messages,*,tokenize,add_generation_prompt):
            result=original(messages,tokenize=tokenize,add_generation_prompt=add_generation_prompt)
            return result+'changed' if add_generation_prompt else result
        tok.apply_chat_template=changed
        with self.assertRaisesRegex(InstructionError,'CHAT_TEMPLATE_PREFIX_MISMATCH'):
            tokenize_example(self.sample(),tok,resources().contract['format'])

    def test_roundtrip_mismatch_fails(self):
        tok=TestTokenizer();tok.decode=lambda ids,**kwargs:'changed'
        with self.assertRaisesRegex(InstructionError,'COMPLETION_ROUNDTRIP_MISMATCH'):
            tokenize_example(self.sample(),tok,resources().contract['format'])

    def test_padding_does_not_mask_a_real_eos_when_pad_equals_eos(self):
        first={'input_ids':[5,6,2],'attention_mask':[1,1,1],'labels':[-100,6,2]}
        second={'input_ids':[5,2],'attention_mask':[1,1],'labels':[-100,2]}
        result=collate([first,second],pad_token_id=2,pad_to_multiple_of=4)
        self.assertEqual(result['labels'],[[-100,6,2,-100],[-100,2,-100,-100]])
        self.assertEqual(result['attention_mask'],[[1,1,1,0],[1,1,0,0]])
        self.assertEqual(set(result),{'input_ids','attention_mask','labels'})

    def test_invalid_or_oversize_batches_fail(self):
        row={'input_ids':[1,2,3],'attention_mask':[1,1,1],'labels':[-100,2,3]}
        with self.assertRaisesRegex(InstructionError,'PADDED_SEQUENCE_TOKEN_LIMIT'):
            collate([row],pad_token_id=0,max_sequence_tokens=3,pad_to_multiple_of=4)
        row['labels']=[-100]*3
        with self.assertRaisesRegex(InstructionError,'INVALID_AUDITED_ENCODING'):
            collate([row],pad_token_id=0)

    def test_download_provenance_detects_changed_bytes_and_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);metadata=folder/'.cache/huggingface/download';metadata.mkdir(parents=True)
            contract=resources().contract
            for name in ('tokenizer.json','tokenizer_config.json','config.json','vocab.json','merges.txt'):
                data=b'{}';(folder/name).write_bytes(data)
                etag=hashlib.sha1(b'blob 2\0'+data).hexdigest()
                (metadata/(name+'.metadata')).write_text(contract['format']['tokenizer_revision']+'\n'+etag+'\n0\n')
            self.assertEqual(len(tokenizer_provenance(folder,contract)['files']),5)
            (folder/'merges.txt').write_bytes(b'changed')
            with self.assertRaisesRegex(InstructionError,'TOKENIZER_BLOB_CHECKSUM_MISMATCH'):
                tokenizer_provenance(folder,contract)
            (folder/'merges.txt').write_bytes(b'{}')
            (metadata/'config.json.metadata').write_text('wrong\nwrong\n')
            with self.assertRaisesRegex(InstructionError,'TOKENIZER_REVISION_MISMATCH'):
                tokenizer_provenance(folder,contract)


class GroupPlannerTests(unittest.TestCase):
    def production_rows(self,tmp):
        first,res=production_resource(tmp);rows=[first]
        for number,chapter in [(2,'ch03.pdf'),(3,'ch05.pdf')]:
            row=record(number);context=row['contexts'][0]
            row.update(record_id=f'W5_A_{number:05d}',course_code='THMLN',source_identity_scope='offline_corpus',source_group_ids=['THMLN:'+chapter])
            context.update(source_checksum=first['contexts'][0]['source_checksum'],rights_reference='UNVERIFIED:THMLN:'+chapter)
            source=deepcopy(res.sources[0]);source.update(document_id=context['document_id'],version_id=context['version_id'],source_group_id='THMLN:'+chapter,source_doc=chapter)
            res.sources.append(source);rows.append(rehash(row))
        first['contexts'][0]['rights_reference']='UNVERIFIED:THMLN:ch01.pdf';rehash(first);res.__post_init__()
        return rows,res

    def test_deterministic_order_independent_whole_source_plan(self):
        rows=[record(i) for i in range(1,7)]
        rows[1]['contexts'][0]['document_id']=rows[0]['contexts'][0]['document_id']
        rehash(rows[1])
        plan,report=make_plan(rows,resources().contract)
        again,_=make_plan(list(reversed(rows)),resources().contract)
        self.assertEqual(plan,again)
        self.assertEqual(plan['assignments'][rows[0]['record_id']],plan['assignments'][rows[1]['record_id']])
        self.assertEqual(report['component_count'],5)
        self.assertEqual(sum(report['split_counts'].values()),6)
        validate_plan(rows,plan,resources().contract)

    def test_three_sources_stay_nonempty_without_forcing_eighty_percent(self):
        rows=[record(i) for i in range(1,4)]
        _,report=make_plan(rows,resources().contract)
        self.assertEqual(sorted(report['split_counts'].values()),[1,1,1])

    def test_too_few_components_and_missing_parent_fail(self):
        with self.assertRaisesRegex(InstructionError,'GROUP_PLANNER_REQUIRES'):
            make_plan([record(),record(2)],resources().contract)
        row=record();row['parent_record_id']='W5_A_99999'
        with self.assertRaisesRegex(InstructionError,'PARENT_NOT_INCLUDED'):
            connected_components([row])

    def test_reported_objective_matches_exhaustive_minimum(self):
        rows=[record(i) for i in range(1,5)];contract=resources().contract
        _,report=make_plan(rows,contract);costs=[]
        for assignment in product(range(3),repeat=4):
            if len(set(assignment))!=3:continue
            cost=0
            for split,ratio in enumerate((0.8,0.1,0.1)):
                n=assignment.count(split)
                # One course and one task: sample(4), course(1), task(0.25).
                cost+=5.25*(n-ratio*4)**2
            costs.append(cost)
        self.assertAlmostEqual(report['objective_value'],min(costs))

    def test_failed_token_audit_never_publishes_ready_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows,res=self.production_rows(tmp)
            output=Path(tmp)/'.private/instruction/prepared'
            with patch('scripts.instruction.common.read_pdf_pages',return_value=[rows[0]['contexts'][0]['text']]),patch('scripts.instruction.prepare_sft.tokenize_example',side_effect=InstructionError('TOKEN_TEST_FAILURE')):
                with self.assertRaisesRegex(InstructionError,'TOKEN_TEST_FAILURE'):
                    prepare(rows,reviews(rows),output,res,TestTokenizer(),{'unit_test':True})
            self.assertFalse(output.exists())
            self.assertFalse(any(output.parent.glob('.prepare-*')))

    def test_prepared_package_has_hash_bound_encodings_and_contract_snapshot(self):
        from scripts.instruction.common import canonical
        with tempfile.TemporaryDirectory() as tmp:
            rows,res=self.production_rows(tmp);output=Path(tmp)/'.private/instruction/prepared'
            with patch('scripts.instruction.common.read_pdf_pages',return_value=[rows[0]['contexts'][0]['text']]):
                result=prepare(rows,reviews(rows),output,res,TestTokenizer(),{'verification':'UNIT_TEST_ONLY'})
            self.assertTrue(result['training_ready'])
            self.assertFalse(result['group_release_ready'])
            self.assertEqual(result['validation']['training'],'NOT_RUN')
            self.assertEqual(result['validation']['final_b_review'],'PENDING')
            self.assertEqual(result['input_sha256']['contract'],digest(canonical(read_json(output/'input-contract.snapshot.json'))))
            for name,entry in result['files'].items():
                self.assertEqual(digest((output/name).read_bytes()),entry['sha256'])
                self.assertEqual((output/name).stat().st_size,entry['size_bytes'])
            audit=read_json(output/'tokenization-audit.json')
            self.assertEqual(len(audit['rows']),3)
            for summary in audit['rows']:
                encoded=read_jsonl(output/'tokenized'/(summary['split']+'.jsonl'))[summary['row_index']]
                self.assertEqual(summary['record_id'],encoded.pop('record_id'))
                self.assertEqual(summary['encoded_sha256'],digest(canonical(encoded)))
