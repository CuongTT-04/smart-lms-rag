import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from scripts.w6 import handoff


class HandoffIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'README.md').write_text('Private handoff.')
        raw=(self.root/'README.md').read_bytes()
        m={'files':{'README.md':{'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)}}}
        (self.root/'package-manifest.json').write_text(json.dumps(m))
        self.sha=hashlib.sha256((self.root/'package-manifest.json').read_bytes()).hexdigest()
        (self.root/'SHA256SUMS.txt').write_text(m['files']['README.md']['sha256']+'  README.md\n'+self.sha+'  package-manifest.json\n')

    def test_manifest_checksum_and_exact_file_set_are_verified(self):
        result=handoff.verify_tree(self.root,self.sha)
        self.assertEqual(result['files_checked'],1)

    def test_modified_code_or_data_is_rejected(self):
        (self.root/'README.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'PACKAGE_MEMBER_INTEGRITY'):
            handoff.verify_tree(self.root,self.sha)

    def test_unlisted_sensitive_file_is_rejected(self):
        (self.root/'.env').write_text('secret fixture')
        with self.assertRaisesRegex(ValueError,'PACKAGE_FILE_SET'):
            handoff.verify_tree(self.root,self.sha)

    def test_wrong_receipt_manifest_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'PACKAGE_MANIFEST_HASH'):
            handoff.verify_tree(self.root,'0'*64)

    def test_checksum_list_cannot_omit_a_file(self):
        (self.root/'SHA256SUMS.txt').write_text(self.sha+'  package-manifest.json\n')
        with self.assertRaisesRegex(ValueError,'PACKAGE_SUM_SET'):
            handoff.verify_tree(self.root,self.sha)

    def test_archive_name_preserves_dotted_version(self):
        self.assertEqual(handoff.archive_path(Path('W6-Cuong-to-Duong-v1.0')),
                         Path('W6-Cuong-to-Duong-v1.0.zip'))

    def test_build_includes_trainer_plan_referenced_by_guide(self):
        from scripts.w6.contracts import write_json,sha_file
        repo=self.root/'repo';pilot=self.root/'pilot';output=self.root/'handoff-v1.0'
        for name in ('data/w6/training-contract.json','data/w6/source-allocation.json',
                     'data/w6/record-allocation.csv','registry.json',
                     'docs/weekly/W6/phan-cong-w6.md','scripts/w6/README.md'):
            path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
        contract={'source_code_sha256':{},'source_manifest':{'path':'registry.json'}}
        write_json(pilot/'training-contract.json',contract)
        write_json(pilot/'tokenizer-reference.json',{'files':{}})
        write_json(pilot/'manifest.json',{'files':{'training-contract.json':{},'tokenizer-reference.json':{}},
                    'counts':{'train':128,'validation':32},'source_archive_sha256':'fixture'})
        (pilot/'SHA256SUMS.txt').write_text('fixture')
        report=self.root/'verification.json';write_json(report,{'passed':True,'manifest_sha256':sha_file(pilot/'manifest.json')})
        with patch.object(handoff,'ROOT',repo):
            archive,_=handoff.build(pilot,self.root/'tokenizer',output,self.root/'README.md',report)
        self.assertTrue(archive.is_file())
        self.assertEqual((output/'docs/weekly/W6/phan-cong-w6.md').read_text(),'fixture')


if __name__=='__main__':unittest.main()
