from pathlib import Path
from copy import deepcopy
import tempfile
import unittest
from unittest.mock import patch

from scripts.instruction.common import InstructionError, validate_record
from scripts.instruction.export_sft_dataset import export
from scripts.instruction.generate_candidates import generate
from scripts.instruction.tests.support import draft, plan, production_resource, record, rehash, reviews


class PrivateDraftTests(unittest.TestCase):
    def prepare(self, folder):
        row, res = production_resource(folder)
        res.contract['source_rights']['private_research_drafts'] = {
            'allowed': True, 'training_allowed': False, 'redistribution_allowed': False}
        res.sources[0].update(generation_authorized=False, rights_status='DECLARED_NOT_VERIFIED',
                              rights_evidence_reference=None)
        row['contexts'][0]['rights_reference'] = 'UNVERIFIED:THMLN:ch01.pdf'
        return rehash(row), res

    def test_private_draft_retains_unverified_rights_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            row, res = self.prepare(tmp)
            output = Path(tmp)/'.private/instruction/pilot.jsonl'
            with patch('scripts.instruction.common.read_pdf_pages', return_value=[row['contexts'][0]['text']]):
                result = generate([draft(row)], output, res, private_draft=True)
                before = output.read_bytes()
                again = generate([draft(row)], output, res, private_draft=True)
            self.assertEqual(result['status'], 'PRIVATE_DRAFT_RIGHTS_UNVERIFIED')
            self.assertEqual(again['added_count'], 0)
            self.assertEqual(before, output.read_bytes())
            self.assertFalse(res.sources[0]['generation_authorized'])
            self.assertIsNone(res.sources[0]['rights_evidence_reference'])

    def test_private_flag_requires_explicit_contract_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            row, res = self.prepare(tmp)
            res.contract['source_rights']['private_research_drafts']['allowed'] = False
            with self.assertRaisesRegex(InstructionError, 'PRIVATE_DRAFT_NOT_AUTHORIZED'):
                validate_record(row, res, private_draft=True)

    def test_private_draft_cannot_be_written_outside_private_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            row, res = self.prepare(tmp)
            with self.assertRaisesRegex(InstructionError, 'PRIVATE_DRAFT_OUTPUT_MUST_STAY_PRIVATE'):
                generate([draft(row)], Path(tmp)/'public.jsonl', res, private_draft=True)

    def test_private_draft_does_not_bypass_source_or_target_integrity(self):
        for kind in ('text', 'target', 'marker'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                row, res = self.prepare(tmp)
                original_text = row['contexts'][0]['text']
                if kind == 'text': row['contexts'][0]['text'] = 'changed'
                if kind == 'target': row['target_text'] = 'Missing citation'
                if kind == 'marker': row['contexts'][0]['rights_reference'] = 'APPROVED'
                with patch('scripts.instruction.common.read_pdf_pages', return_value=[original_text]), self.assertRaises(InstructionError):
                    validate_record(rehash(row), res, private_draft=True)

    def test_private_draft_cannot_use_fixture_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            row, res = self.prepare(tmp)
            with self.assertRaisesRegex(InstructionError, 'PRIVATE_DRAFT_IS_NOT_FIXTURE'):
                validate_record(row, res, private_draft=True, preview=True)

    def test_sft_export_cannot_promote_unverified_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            row, res = self.prepare(tmp)
            output = Path(tmp)/'export'
            with self.assertRaisesRegex(InstructionError, 'SOURCE_RIGHTS_UNVERIFIED'):
                export([row], reviews([row]), plan([row]), output, res)
            self.assertFalse(output.exists())

    def test_internal_research_export_is_explicit_private_and_pending_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            row,res=self.prepare(tmp);rows=[row]
            for number,chapter in [(2,'ch03.pdf'),(3,'ch05.pdf')]:
                other=record(number)
                other.update(record_id=f'W5_A_{number:05d}',course_code='THMLN',
                    source_identity_scope='offline_corpus',source_group_ids=['THMLN:'+chapter])
                context=other['contexts'][0]
                context.update(source_checksum=row['contexts'][0]['source_checksum'],
                    rights_reference='UNVERIFIED:THMLN:'+chapter)
                source=deepcopy(res.sources[0]);source.update(document_id=context['document_id'],
                    version_id=context['version_id'],source_group_id='THMLN:'+chapter,source_doc=chapter)
                res.sources.append(source);rows.append(rehash(other))
            res.__post_init__();output=Path(tmp)/'.private/instruction/export'
            with patch('scripts.instruction.common.read_pdf_pages',return_value=[row['contexts'][0]['text']]):
                result=export(rows,reviews(rows),plan(rows),output,res,internal_research=True)
            self.assertEqual(result['status'],'INTERNAL_RESEARCH_CANDIDATE_PENDING_AUDIT')
            self.assertFalse(result['training_ready'])
            self.assertFalse(result['rights_verified_by_export'])
            self.assertFalse(result['public_redistribution_allowed'])
            self.assertEqual(result['source_rights_status'],'DECLARED_NOT_VERIFIED')
            self.assertEqual(result['validation']['final_b_review'],'PENDING')
            self.assertEqual(len(list(output.iterdir())),5)

    def test_internal_research_requires_policy_and_private_output(self):
        for kind,code in [('disabled','INTERNAL_RESEARCH_NOT_AUTHORIZED'),
                          ('public','RESEARCH_OUTPUT_MUST_STAY_PRIVATE'),
                          ('fixture','RESEARCH_IS_NOT_FIXTURE')]:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                row,res=self.prepare(tmp);output=Path(tmp)/'.private/instruction/export'
                if kind=='disabled':res.contract['source_rights']['internal_research']['enabled']=False
                if kind=='public':output=Path(tmp)/'public-export'
                with self.assertRaisesRegex(InstructionError,code):
                    export([row],reviews([row]),plan([row]),output,res,internal_research=True,preview=kind=='fixture')
                self.assertFalse(output.exists())

    def test_internal_research_still_requires_current_self_review_and_valid_plan(self):
        for kind,code in [('review','SELF_REVIEW_MISSING_OR_STALE'),('split','INVALID_SPLIT_PLAN')]:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                row,res=self.prepare(tmp);scores=reviews([row])
                if kind=='review':scores[0]['content_sha256']='0'*64
                with patch('scripts.instruction.common.read_pdf_pages',return_value=[row['contexts'][0]['text']]),self.assertRaisesRegex(InstructionError,code):
                    export([row],scores,{},Path(tmp)/'.private/instruction/export',res,internal_research=True)
