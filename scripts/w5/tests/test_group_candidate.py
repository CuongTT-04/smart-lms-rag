import copy
import unittest
from scripts.w5.group_candidate import source_excerpt_matches, balanced_plan, candidate_status, verify_group_package, tokenizer_contract
from scripts.w5.common import load_contract,ROOT
import json,hashlib,tempfile
from pathlib import Path


class GroupCandidateTests(unittest.TestCase):
    def test_tokenizer_settings_come_only_from_frozen_w5_contract(self):
        frozen=load_contract(ROOT/'data/instruction/w5/contract')
        mapped=tokenizer_contract(frozen)['format']
        self.assertEqual(mapped['tokenizer_revision'],frozen['training']['tokenizer_revision'])
        self.assertEqual(mapped['transformers_reference'],'4.57.6')
        self.assertEqual(mapped['max_prompt_tokens'],3072)
        self.assertEqual(mapped['max_completion_tokens'],768)
        self.assertEqual(mapped['max_sequence_tokens'],4096)

    def test_conflicting_revision_and_invalid_limits_rejected(self):
        for field,value in [('tokenizer_revision','wrong'),('max_prompt_tokens',99999)]:
            frozen=load_contract(ROOT/'data/instruction/w5/contract');frozen['training'][field]=value
            with self.assertRaises(ValueError):tokenizer_contract(frozen)

    def test_ocr_whitespace_keeps_all_non_whitespace_characters(self):
        self.assertTrue(source_excerpt_matches('giai c ấp công nhân', 'giai cấp công nhân'))
        self.assertFalse(source_excerpt_matches('có lợi nhuận', 'không có lợi nhuận'))
        self.assertFalse(source_excerpt_matches('năm 2024', 'năm 2025'))

    def records(self):
        return [dict(record_id=f'{c}{i}', content_sha256=str(i),course_code=c,task_type='qa',
                     source_group_ids=[f'{c}:{i}'],variant_family_id=f'{c}-{i}',parent_record_id=None)
                for c in ['THMLN','KTCTMLN','CNXHKH'] for i in range(4)]

    def test_plan_is_deterministic_disjoint_and_all_courses_covered(self):
        rows=self.records();original=copy.deepcopy(rows)
        plan=balanced_plan(rows)
        self.assertEqual(plan,balanced_plan(list(reversed(rows))))
        self.assertEqual(rows,original)
        all_ids=[]
        for ids in plan['splits'].values():
            all_ids+=ids
            self.assertEqual({r['course_code'] for r in rows if r['record_id'] in ids}, {'THMLN','KTCTMLN','CNXHKH'})
        self.assertEqual(len(all_ids),len(set(all_ids)))
        self.assertEqual(set(all_ids),{r['record_id'] for r in rows})

    def test_related_source_groups_stay_in_one_component(self):
        rows=self.records();rows[1]['source_group_ids']=rows[0]['source_group_ids']
        plan=balanced_plan(rows)
        self.assertTrue(any({'THMLN0','THMLN1'}<=set(ids) for ids in plan['splits'].values()))

    def test_insufficient_course_components_fail_without_faking_coverage(self):
        with self.assertRaises(ValueError):balanced_plan(self.records()[:2])

    def test_token_pass_does_not_grant_acceptance(self):
        status=candidate_status(500)
        self.assertFalse(status['group_release_ready'])
        self.assertFalse(status['training_ready'])
        self.assertEqual(status['peer_acceptance'],'PENDING_ACTUAL_MEMBERS')

    def test_readback_rejects_tampered_files_before_loading_tokenizer(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'data.json').write_text('changed')
            m=dict(candidate_status(500),files={'data.json':{'sha256':'0'*64,'size_bytes':7}})
            path=folder/'manifest.json';path.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,'File checksum'):
                verify_group_package(folder,folder,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_readback_rejects_fabricated_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);m=dict(candidate_status(500),files={});m['group_release_ready']=True
            path=folder/'manifest.json';path.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,'approval'):
                verify_group_package(folder,folder,hashlib.sha256(path.read_bytes()).hexdigest())
