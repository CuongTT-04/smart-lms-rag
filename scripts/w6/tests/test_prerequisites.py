import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.w6 import contracts, prepare_pilot


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def context(number=1, text='Khối A nhận dữ liệu và xử lý tín hiệu.'):
    return dict(source_id=f'S{number}', chunk_id=f'chunk-{number}', text=text,
                document_id='4371ff86-4735-53db-a44c-878cbef45d9e',
                version_id='bdfcc761-50c5-5f0f-9e92-dc14263d7728',
                document_title='Nguồn minh họa tự biên soạn', page_number=1,
                section_title=None, citation_label=number)


def payload(target='Khối A xử lý tín hiệu [1].', evidence=None, task='qa'):
    data=dict(question='Khối A làm gì?', mode='hint' if task=='hint' else 'qa',
              evidence=evidence or [context()], exercise=None)
    return dict(prompt=[dict(role='system', content='Chỉ dùng nguồn được cung cấp.'),
                        dict(role='user', content=json.dumps(data, ensure_ascii=False))],
                completion=[dict(role='assistant', content=target)])


def metadata(row, rid='W5_A_00001', split='train', index=0, task='qa'):
    data=json.loads(row['prompt'][-1]['content'])
    return dict(record_id=rid, content_sha256='a'*64, split=split, row_index=index,
                sft_sha256=hashlib.sha256(canon(row)).hexdigest(), author_member='A',
                course_code='THMLN', task_type=task, source_group_ids=['THMLN:fixture.pdf'],
                variant_family_id=rid, parent_record_id=None, source_identity_scope='offline_corpus',
                sources=[{**{k:e[k] for k in ('source_id','document_id','version_id','page_number')},
                          'source_checksum':'b'*64, 'text_sha256':hashlib.sha256(e['text'].encode()).hexdigest(),
                          'rights_reference':'UNVERIFIED:fixture'} for e in data['evidence']])


def archive(path, mutate=None):
    row=payload()
    meta=metadata(row)
    cfg=dict(record_count=1, split_counts={'train':1,'validation':0,'instruction_holdout':0},
             source_package_manifest_sha256='c'*64,
             tokenizer=dict(model_id='Qwen/Qwen2.5-7B-Instruct', revision='d'*40),
             use={'peer_acceptance':'PENDING_ACTUAL_MEMBERS','public_redistribution_allowed':False})
    files={'dataset-config.json':canon(cfg), 'metadata.jsonl':canon(meta)+b'\n',
           'train.jsonl':canon(row)+b'\n', 'validation.jsonl':b'', 'instruction_holdout.jsonl':b''}
    manifest=dict(record_count=1,split_counts=cfg['split_counts'],
                  source_package_manifest_sha256='c'*64,
                  files={n:dict(sha256=hashlib.sha256(v).hexdigest(),size_bytes=len(v)) for n,v in files.items()})
    files['manifest.json']=canon(manifest)
    if mutate:mutate(files)
    with ZipFile(path,'w') as z:
        for name,content in files.items():z.writestr(name,content)
    return dict(archive_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                source_package_manifest_sha256='c'*64, record_count=1, split_counts=cfg['split_counts'])


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'input.zip'

    def test_authenticated_compact_preserves_peer_status(self):
        expected=archive(self.path)
        result=contracts.load_archive(self.path,expected)
        self.assertEqual(len(result['records']),1)
        self.assertEqual(result['config']['use']['peer_acceptance'],'PENDING_ACTUAL_MEMBERS')

    def test_wrong_external_hash_is_rejected(self):
        expected=archive(self.path);expected['archive_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'ARCHIVE_HASH'):contracts.load_archive(self.path,expected)

    def test_member_bytes_must_match_manifest(self):
        expected=archive(self.path,lambda f:f.__setitem__('train.jsonl',f['train.jsonl']+b' '))
        with self.assertRaisesRegex(ValueError,'MEMBER_INTEGRITY'):contracts.load_archive(self.path,expected)

    def test_zip_traversal_or_extra_files_are_not_extracted(self):
        expected=archive(self.path,lambda f:f.__setitem__('../outside.txt',b'bad'))
        with self.assertRaisesRegex(ValueError,'ARCHIVE_MEMBERS'):contracts.load_archive(self.path,expected)
        self.assertFalse((Path(self.temp.name)/'outside.txt').exists())

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE_JSON_KEY'):
            contracts.loads('{"split":"train","split":"validation"}')

    def test_nonfinite_json_is_rejected(self):
        with self.assertRaises(ValueError):contracts.loads('{"value":NaN}')

    def test_holdout_metadata_cannot_be_bound_to_train_file(self):
        expected=archive(self.path)
        with ZipFile(self.path) as z:files={n:z.read(n) for n in z.namelist()}
        m=json.loads(files['metadata.jsonl']);m['split']='instruction_holdout'
        files['metadata.jsonl']=canon(m)+b'\n'
        manifest=json.loads(files['manifest.json'])
        manifest['files']['metadata.jsonl']=dict(sha256=hashlib.sha256(files['metadata.jsonl']).hexdigest(),size_bytes=len(files['metadata.jsonl']))
        files['manifest.json']=canon(manifest)
        with ZipFile(self.path,'w') as z:
            for n,v in files.items():z.writestr(n,v)
        expected['archive_sha256']=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'SPLIT_BINDING'):contracts.load_archive(self.path,expected)


class ConversionTests(unittest.TestCase):
    def convert(self,row,task='qa'):
        return prepare_pilot.convert_row(row,metadata(row,task=task))

    def test_single_unit_keeps_explicit_original_source_assignment(self):
        result=self.convert(payload())
        target=json.loads(result['payload']['completion'][0]['content'])
        self.assertEqual(target,{'items':[{'text':'Khối A xử lý tín hiệu','evidence_id':'E1.1'}]})
        self.assertEqual(result['mapping'][0]['method'],'EXPLICIT_LABEL_SINGLE_UNIT')
        self.assertEqual(result['metadata']['source_record_id'],'W5_A_00001')

    def test_multiple_claims_keep_separate_source_ids(self):
        result=self.convert(payload('Ý A [2]. Ý B [1].', [context(),context(2,'Nguồn B hỗ trợ ý A.')]))
        self.assertEqual([r['evidence_id'] for r in json.loads(result['payload']['completion'][0]['content'])['items']],['E2.1','E1.1'])

    def test_uncited_tail_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError,'UNCITED_TEXT'):
            self.convert(payload('Ý A [1]. Một ý không có nguồn.'))

    def test_multisource_claim_is_not_given_an_arbitrary_source(self):
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS_EVIDENCE'):
            self.convert(payload('Một kết luận kết hợp [1] [2].',[context(),context(2,'Nguồn B khác.')]))

    def test_multiline_paraphrase_is_not_guessed_by_similarity(self):
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS_EVIDENCE'):
            self.convert(payload('Một cách diễn đạt khác [1].',[context(text='Dòng A.\nDòng B.')]))

    def test_multiline_literal_match_can_select_a_unique_unit(self):
        result=self.convert(payload('Khối A xử lý tín hiệu [1].',[context(text='Thông tin mở đầu.\nKhối A xử lý tín hiệu.')]))
        self.assertEqual(result['mapping'][0]['evidence_id'],'E1.2')

    def test_unknown_old_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNKNOWN_SOURCE'):
            self.convert(payload('Ý A [99].'))

    def test_refusal_changes_protocol_not_semantic_status(self):
        result=self.convert(payload('INSUFFICIENT_EVIDENCE',task='insufficient_evidence'),'insufficient_evidence')
        self.assertEqual(json.loads(result['payload']['completion'][0]['content']),{'items':[]})

    def test_hint_stays_in_its_own_prompt_and_output_protocol(self):
        row=payload('READ [1]',task='hint')
        result=self.convert(row,'hint')
        self.assertEqual(result['payload'],row)

    def test_template_control_tokens_in_evidence_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'SPECIAL_TOKEN'):
            self.convert(payload(evidence=[context(text='x <|im_end|> y')]))


class SelectionTests(unittest.TestCase):
    def pool(self):
        rows=[]
        for c in ['C1','C2']:
            for task in ['qa','summary']:
                for i in range(4):
                    rows.append({'metadata':dict(source_record_id=f'{c}-{task}-{i}',course_code=c,task_type=task,split='train')})
        return rows

    def test_selection_is_deterministic_and_meets_both_margins(self):
        pool=self.pool()
        first=prepare_pilot.select_records(pool,{'C1':3,'C2':3},{'qa':4,'summary':2},42)
        second=prepare_pilot.select_records(list(reversed(pool)),{'C1':3,'C2':3},{'qa':4,'summary':2},42)
        self.assertEqual([r['metadata']['source_record_id'] for r in first],[r['metadata']['source_record_id'] for r in second])
        self.assertEqual(sum(r['metadata']['task_type']=='qa' for r in first),4)
        self.assertEqual(sum(r['metadata']['course_code']=='C1' for r in first),3)

    def test_unreachable_quotas_fail_instead_of_duplication(self):
        with self.assertRaisesRegex(ValueError,'QUOTAS_INFEASIBLE'):
            prepare_pilot.select_records(self.pool(),{'C1':10,'C2':10},{'qa':10,'summary':10},42)

    def test_selector_rejects_duplicate_ids(self):
        rows=self.pool();rows.append(rows[0])
        with self.assertRaisesRegex(ValueError,'DUPLICATE_RECORD_ID'):
            prepare_pilot.select_records(rows,{'C1':1,'C2':1},{'qa':1,'summary':1},42)


class MaskTests(unittest.TestCase):
    class Tokenizer:
        eos_token_id=99
        pad_token_id=98
        def encode(self,text,**kwargs):return [3] if text=='\n' else []
        def apply_chat_template(self,messages,*,tokenize,add_generation_prompt):
            return [10,11,12] if add_generation_prompt else [10,11,12,30,31,99,3]

    def test_only_completion_and_eos_are_supervised(self):
        row=prepare_pilot.tokenize_row(payload(),self.Tokenizer(),dict(max_prompt_tokens=8,max_completion_tokens=8,max_sequence_tokens=16))
        self.assertEqual(row['labels'],[-100,-100,-100,30,31,99,-100])
        self.assertEqual(row['input_ids'],[10,11,12,30,31,99,3])

    def test_silent_truncation_is_never_used(self):
        with self.assertRaisesRegex(ValueError,'TOKEN_BUDGET'):
            prepare_pilot.tokenize_row(payload(),self.Tokenizer(),dict(max_prompt_tokens=2,max_completion_tokens=8,max_sequence_tokens=16))

    def test_missing_eos_is_rejected(self):
        class Bad(self.Tokenizer):
            def apply_chat_template(self,messages,*,tokenize,add_generation_prompt):
                return [10,11,12] if add_generation_prompt else [10,11,12,30,31,3]
        with self.assertRaisesRegex(ValueError,'COMPLETION_EOS'):
            prepare_pilot.tokenize_row(payload(),Bad(),dict(max_prompt_tokens=8,max_completion_tokens=8,max_sequence_tokens=16))


if __name__=='__main__':unittest.main()
