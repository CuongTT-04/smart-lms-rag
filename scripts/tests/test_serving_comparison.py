import json
from pathlib import Path
import tempfile
import unittest

from scripts.serving_comparison import audit, build_cases, digest, fixture_values, technical_checks, record_generation_attempt
from scripts.package_serving_comparison import SETUP, ENVIRONMENT, EXECUTE, EXPORT

ROOT = Path(__file__).resolve().parents[2]


class ServingComparisonTests(unittest.TestCase):
    def test_private_attempt_log_preserves_rejected_output_without_input_prompts(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'generation-attempts.jsonl'
            for number, text in [(1, 'Đầu ra cần loại.'), (2, 'Đầu ra viết lại.')]:
                record_generation_attempt(path, case_id='example', arm='base_rag', number=number,
                    output=SimpleNamespace(text=text, finish_reason='eos',
                        usage=SimpleNamespace(input_tokens=100, output_tokens=20)))
            rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            self.assertEqual([row['attempt'] for row in rows], [1, 2])
            self.assertEqual(rows[0]['text'], 'Đầu ra cần loại.')
            self.assertNotIn('messages', rows[0])
            self.assertNotIn('token', rows[0])

    def setUp(self):
        self.plan = json.loads((ROOT/'data/qa/guardrails-cases.json').read_bytes())
        self.fixture = ROOT/self.plan['fixture']
        self.cases = build_cases(self.plan, self.fixture)

    def test_fixture_read_without_importing_django(self):
        pages = fixture_values(self.fixture)
        self.assertEqual(len(pages['allowed_pages']), 3)
        self.assertIn('Fetch', pages['allowed_pages'][0])
        self.assertIn('W9_PROMPT_INJECTION_MARKER', pages['allowed_pages'][2])

    def test_requests_cover_generation_not_permissions(self):
        rows = self.cases['requests']
        self.assertEqual(len(rows), 14)
        self.assertEqual(len({r['id'] for r in rows}), 14)
        ids = {r['case_id'] for r in rows}
        self.assertEqual(len(ids), 13)
        self.assertEqual(ids | set(self.cases['deferred_cases']), {c['id'] for c in self.plan['cases']})
        self.assertIn('GR-06', self.cases['deferred_cases'])
        for row in rows:
            self.assertEqual(row['request_sha256'], digest(dict(endpoint=row['endpoint'],
                payload=row['payload'], contexts=row['contexts'])))

    def test_request_contexts_and_tutoring_match_product_contract(self):
        from apps.ai.rag.base import EvidenceContext
        from apps.ai.rag.conversation import validate_history
        from apps.ai.rag.tutoring import validate_tutoring
        from apps.ai.inference_gateway import public_exercise
        for row in self.cases['requests']:
            for source in row['contexts']:
                EvidenceContext.from_value(source)
            payload = row['payload']
            if 'tutoring' in payload:
                validate_tutoring(payload['tutoring'])
                public_exercise(payload['exercise'])
                self.assertNotIn('history', payload)
            if 'history' in payload:
                validate_history(payload['history'])

    def test_summary_uses_only_selected_page(self):
        row = next(r for r in self.cases['requests'] if r['case_id']=='GR-21')
        self.assertEqual([c['page_number'] for c in row['contexts']], [2])
        self.assertEqual(row['payload']['phase'], 'map')
        self.assertEqual(row['payload']['records'][0]['text'], row['contexts'][0]['text'])

    def test_drafts_are_independent_requests(self):
        rows = [r for r in self.cases['requests'] if r['case_id']=='GR-25']
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]['request_sha256'], rows[1]['request_sha256'])
        self.assertEqual(rows[0]['payload']['tutoring'], rows[1]['payload']['tutoring'])

    def test_reference_check_does_not_claim_semantic_support(self):
        result = technical_checks({'output':{'references':[{'source_id':'S99'}]}}, [{'source_id':'S1'}])
        self.assertEqual(result['invalid_references'], 1)
        self.assertEqual(result['semantic_support'], 'PENDING_REVIEW')

    def test_empty_references_not_given_perfect_score(self):
        result = technical_checks({}, [{'source_id':'S1'}])
        self.assertEqual(result['references'], 0)
        self.assertNotIn('accuracy', result)

    def test_notebook_cells_compile(self):
        for source in (SETUP.replace('__HASH__', repr('a'*64)).replace('__PAYLOAD_HASHES__', '{}')
                       .replace('__SERVING_MANIFEST_HASH__', repr('b'*64)),
                       ENVIRONMENT, EXECUTE, EXPORT):
            compile(source, 'comparison-cell', 'exec')
        self.assertNotIn('NGROK', ENVIRONMENT+EXECUTE)
        self.assertIn("('base_rag','tuned_rag')", EXECUTE)

    def test_input_setup_handles_zip_and_kaggle_expansion(self):
        import contextlib
        import hashlib
        import io
        from unittest.mock import patch
        from zipfile import ZipFile
        for expanded in (False, True):
            with self.subTest(expanded=expanded), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                inputs = root/'input'
                inputs.mkdir()
                payloads = {'serving-input.zip':b'fixture', 'runner.py':b'pass\n',
                            'cases.json':b'{"requests": []}'}
                archive_path = root/'comparison-input.zip'
                with ZipFile(archive_path, 'w') as archive:
                    for name, data in payloads.items():
                        archive.writestr(name, data)
                if expanded:
                    for name, data in payloads.items():
                        (inputs/name).write_bytes(data)
                else:
                    (inputs/'comparison-input.zip').write_bytes(archive_path.read_bytes())
                code = SETUP.replace('__HASH__', repr(hashlib.sha256(archive_path.read_bytes()).hexdigest()))
                code = code.replace('__PAYLOAD_HASHES__', repr({
                    name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}))
                code = code.replace('__SERVING_MANIFEST_HASH__', repr('b'*64))
                code = code.replace("Path('/kaggle/input')", f'Path({str(inputs)!r})')
                code = code.replace("Path('/kaggle/working/ayo-paired-' + EXPECTED[:12])", f'Path({str(root/"working")!r})')
                namespace = {}
                with patch.dict('os.environ'), contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(code, 'setup', 'exec'), namespace)
                self.assertTrue(namespace['RUN'].is_dir())
                self.assertEqual((namespace['WORK']/'runner.py').read_bytes(), b'pass\n')

    def test_recursive_expansion_verifies_files_without_rebuilding_zip(self):
        import contextlib
        import hashlib
        import io
        from unittest.mock import patch
        from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
        for tampered in (False, True):
            with self.subTest(tampered=tampered), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                inputs = root/'input'
                expanded = inputs/'serving-input'
                expanded.mkdir(parents=True)
                source = b'print("verified")\n'
                manifest_bytes = json.dumps({'files':{'startup.py':dict(
                    sha256=hashlib.sha256(source).hexdigest(),size_bytes=len(source))}}).encode()
                buffer = io.BytesIO()
                with ZipFile(buffer,'w',ZIP_DEFLATED) as archive:
                    for name,data in sorted({'manifest.json':manifest_bytes,'startup.py':source}.items()):
                        info = ZipInfo(name,date_time=(1980,1,1,0,0,0))
                        info.compress_type = ZIP_DEFLATED
                        archive.writestr(info,data)
                original = buffer.getvalue()
                payloads = {'runner.py':b'pass\n','cases.json':b'{"requests": []}',
                            'serving-input.zip':original}
                for name in ('runner.py','cases.json'):
                    (inputs/name).write_bytes(payloads[name])
                (expanded/'manifest.json').write_bytes(manifest_bytes)
                (expanded/'startup.py').write_bytes(b'tampered' if tampered else source)
                code = SETUP.replace('__HASH__',repr('a'*64)).replace('__PAYLOAD_HASHES__',repr({
                    name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}))
                code = code.replace('__SERVING_MANIFEST_HASH__',repr(hashlib.sha256(manifest_bytes).hexdigest()))
                code = code.replace("Path('/kaggle/input')",f'Path({str(inputs)!r})')
                code = code.replace("Path('/kaggle/working/ayo-paired-' + EXPECTED[:12])",f'Path({str(root/"working")!r})')
                with patch.dict('os.environ'),contextlib.redirect_stdout(io.StringIO()):
                    if tampered:
                        with self.assertRaisesRegex(RuntimeError,'checksum changed'):
                            exec(compile(code,'recursive-input','exec'),{})
                    else:
                        namespace = {}
                        exec(compile(code,'recursive-input','exec'),namespace)
                        self.assertFalse((namespace['WORK']/'serving-input.zip').exists())
                        self.assertEqual((namespace['WORK']/'serving-expanded/startup.py').read_bytes(),source)

    def make_results(self, root):
        import hashlib
        cases_path = root/'cases.json'
        cases_path.write_text(json.dumps(self.cases))
        for arm in ('base_rag','tuned_rag'):
            directory = root/arm
            directory.mkdir()
            identity = dict(adapter_sha256=None if arm=='base_rag' else self.cases['adapter_sha256'],
                tensor_values_match=True, loaded_adapter_tensors=392, active_adapter='default', trainable_parameters=0)
            metadata = dict(arm=arm, identity=identity, cases_sha256=hashlib.sha256(cases_path.read_bytes()).hexdigest(),
                config_sha256='config', config={}, gateway_sha256='gateway', tokenizer_sha256='tokenizer',
                checkpoint_manifest_sha256='checkpoint',seed=42,device='cuda:0')
            (directory/'metadata.json').write_text(json.dumps(metadata))
            rows = [dict(id=r['id'],arm=arm,request_sha256=r['request_sha256'],http=200,seconds=1)
                    for r in self.cases['requests']]
            rows[0]['http'] = 503
            (directory/'results.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
        return cases_path

    def test_audit_retains_failures_and_leaves_selection_pending(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            summary = audit(root, self.make_results(root))
            self.assertEqual(summary['arms']['base_rag']['total'], 14)
            self.assertEqual(summary['arms']['base_rag']['failures'], 1)
            self.assertEqual(summary['quality_acceptance'], 'NOT_DECIDED')
            self.assertEqual(summary['selection'], 'KEEP_BASE_PENDING_REVIEW')

    def test_audit_rejects_missing_or_duplicate_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cases = self.make_results(root)
            path = root/'tuned_rag/results.jsonl'
            rows = path.read_text().splitlines()
            path.write_text('\n'.join(rows[:-1]+[rows[0]]))
            with self.assertRaises(ValueError):
                audit(root, cases)

    def test_audit_rejects_different_generation_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cases = self.make_results(root)
            path = root/'tuned_rag/metadata.json'
            data = json.loads(path.read_bytes())
            data['config_sha256'] = 'changed'
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                audit(root, cases)

    def test_audit_rejects_wrong_adapter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cases = self.make_results(root)
            path = root/'tuned_rag/metadata.json'
            data = json.loads(path.read_bytes())
            data['identity']['adapter_sha256'] = 'wrong'
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                audit(root, cases)


if __name__ == '__main__':
    unittest.main()
