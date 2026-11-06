"""Regression checks for consistently rehashed payload/sidecar substitutions."""
from copy import deepcopy
import unittest
from scripts.qlora.data import digest

class CandidatePayloadBindingTests(unittest.TestCase):
    def fixture(self):
        record=dict(author_member='B',course_code='THMLN',task_type='qa',variant_family_id='f1',contexts=[dict(source_id='S1',document_id='d',version_id='v',page_number=2,source_checksum='a'*64,text_sha256='b'*64,rights_reference='internal')])
        payload=dict(prompt=[dict(role='user',content='question one; evidence E1.1')],completion=[dict(role='assistant',content='{"items":[{"text":"claim","evidence_id":"E1.1"}]}')])
        meta={k:record[k] for k in ('author_member','course_code','task_type','variant_family_id')}
        meta.update(sources=deepcopy(record['contexts']),sft_sha256=digest(payload),training_payload_sha256=digest(payload))
        return record,payload,meta

    def test_rehashed_same_split_swapped_payload_rejected(self):
        from scripts.instruction.expand import validate_payload_binding
        record,expected,meta=self.fixture();swapped=deepcopy(expected);swapped['prompt'][0]['content']='question TWO; evidence E2.1'
        meta.update(sft_sha256=digest(swapped),training_payload_sha256=digest(swapped))
        with self.assertRaisesRegex(ValueError,'AUTHORED_PAYLOAD_RECOMPUTATION'):
            validate_payload_binding(record,swapped,meta,expected)

    def test_wrong_evidence_and_malformed_protocol_rejected(self):
        from scripts.instruction.expand import validate_payload_binding
        for completion in ('{"items":[{"text":"claim","evidence_id":"E9.9"}]}','not JSON'):
            record,expected,meta=self.fixture();bad=deepcopy(expected);bad['completion'][0]['content']=completion
            meta.update(sft_sha256=digest(bad),training_payload_sha256=digest(bad))
            with self.assertRaises(ValueError):validate_payload_binding(record,bad,meta,expected)

    def test_sidecar_task_course_family_source_and_owner_must_match_candidate(self):
        from scripts.instruction.expand import validate_payload_binding
        for key in ('author_member','course_code','task_type','variant_family_id','sources'):
            with self.subTest(key=key):
                record,payload,meta=self.fixture();meta[key]=[] if key=='sources' else 'changed'
                with self.assertRaisesRegex(ValueError,'CANDIDATE_METADATA_BINDING'):
                    validate_payload_binding(record,payload,meta,payload)

    def test_valid_canonical_payload_and_metadata_accepted(self):
        from scripts.instruction.expand import validate_payload_binding
        record,payload,meta=self.fixture();validate_payload_binding(record,payload,meta,payload)

if __name__=='__main__':unittest.main()
