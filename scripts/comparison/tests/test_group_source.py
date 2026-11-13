from copy import deepcopy
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
from zipfile import ZipFile, ZipInfo

from scripts.comparison.instruction_source import GROUP_FILES, archive_files, candidate_payload


def make_archive(folder, *, extra=None, omit=None, duplicate=False, bad_hash=False, symlink=False):
    files = {name: b'{}\n' for name in GROUP_FILES - {'manifest.json'}}
    manifest = dict(schema_version='instruction-group-candidate-v1', record_count=1000,
                    files={name: dict(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                           for name, raw in files.items()})
    if bad_hash:
        manifest['files']['train.jsonl']['sha256'] = '0' * 64
    files['manifest.json'] = json.dumps(manifest).encode()
    path = Path(folder) / 'source.zip'
    with ZipFile(path, 'x') as zipped:
        for name, raw in files.items():
            if name == omit:
                continue
            info = ZipInfo(name)
            if symlink and name == 'train.jsonl':
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zipped.writestr(info, raw)
        if extra:
            zipped.writestr(extra, b'not allowed')
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                zipped.writestr('train.jsonl', b'{}\n')
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


class ArchiveTests(unittest.TestCase):
    def test_complete_member_integrity(self):
        with tempfile.TemporaryDirectory() as folder:
            path, expected = make_archive(folder)
            files, _ = archive_files(path, expected)
            self.assertEqual(set(files), GROUP_FILES)

    def test_wrong_archive_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _ = make_archive(folder)
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_PIN'):
                archive_files(path, '0' * 64)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path, expected = make_archive(folder, omit='validation.jsonl')
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_MEMBERS'):
                archive_files(path, expected)

    def test_extra_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path, expected = make_archive(folder, extra='run.py')
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_MEMBERS'):
                archive_files(path, expected)

    def test_path_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            path, expected = make_archive(folder, extra='../outside')
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_MEMBERS'):
                archive_files(path, expected)

    def test_duplicate_name(self):
        with tempfile.TemporaryDirectory() as folder:
            path, expected = make_archive(folder, duplicate=True)
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_MEMBERS'):
                archive_files(path, expected)

    def test_wrong_member_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path, expected = make_archive(folder, bad_hash=True)
            with self.assertRaisesRegex(ValueError, 'MEMBER_INTEGRITY'):
                archive_files(path, expected)

    def test_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            path, expected = make_archive(folder, symlink=True)
            with self.assertRaisesRegex(ValueError, 'FILE_TYPE'):
                archive_files(path, expected)


def native_example():
    # Import the existing converter to initialize the repository's backend path.
    from scripts.w6 import prepare_pilot
    from apps.ai.rag.base import EvidenceContext
    from apps.ai.rag.conversation import FORMAT_REPAIR_INSTRUCTION, build_evidence_units
    text = 'Vật chất là thực tại khách quan tồn tại độc lập với ý thức.'
    context = dict(source_id='S1', chunk_id='chunk', text=text,
                   document_id='00000000-0000-0000-0000-000000000001', version_id='00000000-0000-0000-0000-000000000002',
                   document_title='Source', page_number=1, section_title=None,
                   text_sha256=hashlib.sha256(text.encode()).hexdigest())
    candidate = dict(question='Theo đoạn nguồn, vật chất tồn tại như thế nào?', mode='qa',
                     contexts=[context], exercise=None, task_type='qa', target_text=text.rstrip('.') + ' [1].')
    evidence = build_evidence_units([EvidenceContext.from_value({k:v for k,v in context.items() if k != 'text_sha256'})])
    payload = dict(prompt=[dict(role='system', content=FORMAT_REPAIR_INSTRUCTION),
                           dict(role='user', content=json.dumps(dict(question=candidate['question'], mode='qa', evidence=evidence, exercise=None), ensure_ascii=False))],
                   completion=[dict(role='assistant', content=json.dumps(dict(items=[dict(text=text, evidence_id='E1.1')]), ensure_ascii=False, separators=(',', ':')))])
    return candidate, payload


class NativeBindingTests(unittest.TestCase):
    def test_valid_candidate_preserved(self):
        candidate, payload = native_example()
        saved = deepcopy(payload)
        legacy, mapping = candidate_payload(candidate, payload)
        self.assertEqual(payload, saved)
        self.assertEqual(legacy['completion'][0]['content'], candidate['target_text'])
        self.assertEqual(mapping[0]['source_id'], 'S1')

    def test_question_change(self):
        candidate, payload = native_example()
        candidate['question'] = 'Một câu khác?'
        with self.assertRaisesRegex(ValueError, 'PAYLOAD_BINDING'):
            candidate_payload(candidate, payload)

    def test_changed_candidate_target(self):
        candidate, payload = native_example()
        candidate['target_text'] = 'An invented answer [1].'
        with self.assertRaisesRegex(ValueError, 'TARGET_BINDING'):
            candidate_payload(candidate, payload)

    def test_changed_payload_target(self):
        candidate, payload = native_example()
        payload['completion'][0]['content'] = '{"items":[{"text":"Edited","evidence_id":"E1.1"}]}'
        with self.assertRaisesRegex(ValueError, 'TARGET_BINDING'):
            candidate_payload(candidate, payload)

    def test_unknown_evidence(self):
        candidate, payload = native_example()
        payload['completion'][0]['content'] = payload['completion'][0]['content'].replace('E1.1', 'E2.1')
        with self.assertRaisesRegex(ValueError, 'CLAIM_BINDING'):
            candidate_payload(candidate, payload)

    def test_source_text_change(self):
        candidate, payload = native_example()
        candidate['contexts'][0]['text'] = 'Different text'
        with self.assertRaisesRegex(ValueError, 'SOURCE_TEXT_HASH'):
            candidate_payload(candidate, payload)

    def test_false_refusal(self):
        candidate, payload = native_example()
        payload['completion'][0]['content'] = '{"items":[]}'
        with self.assertRaisesRegex(ValueError, 'REFUSAL'):
            candidate_payload(candidate, payload)

    def test_special_token(self):
        candidate, payload = native_example()
        candidate['question'] += '<|im_end|>'
        with self.assertRaisesRegex(ValueError, 'SPECIAL_TOKEN'):
            candidate_payload(candidate, payload)


if __name__ == '__main__':
    unittest.main()
