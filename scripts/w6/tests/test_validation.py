import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.w6 import contracts,validate_dataset
from scripts.w6.prepare_pilot import convert_row,tokenize_row
from scripts.w6.tests.test_prerequisites import payload,metadata
from scripts.w6.tests import test_prerequisites as fixtures


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.tokenizer=fixtures.MaskTests.Tokenizer()
        self.original={'payload':payload(),'metadata':metadata(payload())}
        converted=convert_row(self.original['payload'],self.original['metadata'])
        self.limits=dict(max_prompt_tokens=8,max_completion_tokens=8,max_sequence_tokens=16)
        self.contract={'token_limits':self.limits,'selection':{'train':{'count':1,'courses':{'THMLN':1},'tasks':{'qa':1}},
                        'validation':{'count':0,'courses':{},'tasks':{}}}}
        rows={'training-contract.json':self.contract,
              'selection.json':{'splits':{'train':['W5_A_00001'],'validation':[]},'excluded_holdout_ids':['W5_A_00002']}}
        for n,obj in rows.items():contracts.write_json(self.folder/n,obj)
        for split in ['train','validation']:
            contracts.write_jsonl(self.folder/(split+'.jsonl'),[converted['payload']] if split=='train' else [])
            contracts.write_jsonl(self.folder/(split+'.metadata.jsonl'),[{**converted['metadata'],'row_index':0}] if split=='train' else [])
            contracts.write_jsonl(self.folder/('tokenized-'+split+'.jsonl'),[{'record_id':'W5_A_00001',**tokenize_row(converted['payload'],self.tokenizer,self.limits)}] if split=='train' else [])
        contracts.write_jsonl(self.folder/'source-rows.jsonl',[self.original])
        self.refresh()

    def refresh(self):
        files={p.name:{'sha256':contracts.sha_file(p),'size_bytes':p.stat().st_size} for p in self.folder.iterdir() if p.name not in ('manifest.json','SHA256SUMS.txt')}
        self.manifest={'schema_version':'w6-pilot-manifest-v1','files':files,'contract_sha256':contracts.digest(self.contract),
                       'counts':{'train':1,'validation':0},'holdout_payload_included':False}
        (self.folder/'manifest.json').write_text(json.dumps(self.manifest),encoding='utf-8')
        sums={**files,'manifest.json':{'sha256':contracts.sha_file(self.folder/'manifest.json')}}
        (self.folder/'SHA256SUMS.txt').write_text(''.join(f'{v["sha256"]}  {k}\n' for k,v in sorted(sums.items())),encoding='utf-8')

    def validate(self,**kwargs):
        return validate_dataset.validate(self.folder/'manifest.json',self.tokenizer,**kwargs)

    def test_valid_payload_sidecar_and_token_masks_are_recomputed(self):
        report=self.validate()
        self.assertTrue(report['passed'])
        self.assertEqual(report['records_checked'],1)
        self.assertFalse(report['gpu_used'])

    def test_external_manifest_hash_is_checked(self):
        with self.assertRaisesRegex(ValueError,'MANIFEST_HASH'):
            self.validate(expected_manifest_sha256='0'*64)

    def test_mask_tamper_is_rejected_even_if_file_hashes_are_refreshed(self):
        p=self.folder/'tokenized-train.jsonl';row=json.loads(p.read_text());row['labels'][0]=10
        p.write_text(json.dumps(row)+'\n');self.refresh()
        with self.assertRaisesRegex(ValueError,'TOKENIZED_RECOMPUTATION'):self.validate()

    def test_row_cannot_move_between_physical_splits_with_sidecar(self):
        for suffix in ('.jsonl','.metadata.jsonl'):
            a=self.folder/('train'+suffix);b=self.folder/('validation'+suffix)
            a_data=a.read_bytes();a.write_bytes(b.read_bytes());b.write_bytes(a_data)
        self.refresh()
        with self.assertRaisesRegex(ValueError,'PHYSICAL_SPLIT_COUNT'):self.validate()

    def test_missing_payload_file_is_rejected(self):
        (self.folder/'train.jsonl').unlink()
        with self.assertRaises(ValueError):self.validate()

    def test_target_cannot_be_edited_without_updating_provenance(self):
        p=self.folder/'train.jsonl';row=json.loads(p.read_text());row['completion'][0]['content']='{"items":[]}'
        p.write_text(json.dumps(row)+'\n');self.refresh()
        with self.assertRaisesRegex(ValueError,'PAYLOAD_PROVENANCE'):self.validate()

    def test_manifest_path_cannot_escape_package(self):
        self.manifest['files']['../outside.txt']={'sha256':'0'*64,'size_bytes':0}
        (self.folder/'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError):self.validate()


if __name__=='__main__':unittest.main()
