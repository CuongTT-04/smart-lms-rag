import io
import tempfile
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from reportlab.pdfgen.canvas import Canvas
from tests.document_support.models import Course
from apps.documents.services import upload_document, remove_document, retry_ingestion
from apps.documents.models import IngestionJob, DocumentVersion
from apps.documents.processors.parser import ExtractedPage, ExtractionResult, ExtractionError
from apps.documents.worker import claim_job, process_job, recover_expired_jobs, run_parser

class WorkerTests(TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        override=override_settings(DOCUMENTS_STORAGE_ROOT=Path(self.folder.name));override.enable();self.addCleanup(override.disable)
        self.user=get_user_model().objects.create_user(username="teacher")
        self.course=Course.objects.create(teacher=self.user,title="Course")
        buf=io.BytesIO();canvas=Canvas(buf);canvas.drawString(20,700,"PAGE");canvas.showPage();canvas.save()
        self.op=upload_document(self.user,self.course,SimpleUploadedFile("sample.pdf",buf.getvalue()),"Title","upload")
    def result(self,version):
        return ExtractionResult(page_count=1,pages=(ExtractedPage(page_number=1,text="PAGE",status="OK",warnings=()),),
            parser_version="test",checksum_sha256=version.checksum_sha256,ocr_enabled=False)
    def test_claim_once_and_complete_does_not_make_rag_ready(self):
        job=claim_job();self.assertIsNotNone(job);self.assertIsNone(claim_job())
        process_job(job,runner=lambda source,version:self.result(version))
        job.refresh_from_db();self.op.version.refresh_from_db();self.op.document.refresh_from_db()
        self.assertEqual(job.status,"SUCCEEDED");self.assertEqual(self.op.version.status,"EXTRACTED")
        self.assertIsNone(self.op.version.indexed_at);self.assertIsNone(self.op.document.active_version_id)
        self.assertTrue((Path(self.folder.name)/self.op.version.extracted_storage_key).is_file())
    def test_conversion_failure_can_retry_once_with_same_key(self):
        job=claim_job()
        def fail(*args):raise ExtractionError("OCR_REQUIRED","Scanned PDF")
        process_job(job,runner=fail);job.refresh_from_db();self.assertEqual(job.error_code,"OCR_REQUIRED")
        self.op.version.refresh_from_db()
        first=retry_ingestion(self.user,self.op.document,self.op.version,"retry")
        second=retry_ingestion(self.user,self.op.document,self.op.version,"retry")
        self.assertEqual(first.job_id,second.job_id);self.assertEqual(DocumentVersion.objects.count(),1)
    def test_removal_during_extraction_cannot_revive_source(self):
        job=claim_job()
        def remove_then_return(source,version):
            remove_document(self.user,self.op.document)
            return self.result(version)
        process_job(job,runner=remove_then_return);job.refresh_from_db();self.op.version.refresh_from_db()
        self.assertEqual(job.status,"CANCELLED");self.assertEqual(self.op.version.status,"REMOVED")
        self.assertEqual(self.op.version.extracted_storage_key,"")
    def test_lease_recovery_blocks_old_worker(self):
        job=claim_job();IngestionJob.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(recover_expired_jobs(),1)
        process_job(job,runner=lambda source,version:self.result(version))
        job.refresh_from_db();self.assertEqual(job.status,"FAILED");self.assertEqual(job.error_code,"WORKER_INTERRUPTED")
    def test_checksum_mismatch_fails(self):
        job=claim_job()
        source=Path(self.folder.name)/self.op.version.original_storage_key;source.write_bytes(b"changed")
        process_job(job,runner=lambda source,version:self.result(version))
        job.refresh_from_db();self.assertEqual(job.error_code,"SOURCE_CHANGED")
    def test_timeout_records_failure(self):
        job=claim_job()
        def timeout(*args):raise ExtractionError("TIMEOUT","Timeout")
        process_job(job,runner=timeout);job.refresh_from_db()
        self.assertEqual(job.status,"FAILED");self.assertEqual(job.error_code,"TIMEOUT")
    def test_parser_subprocess_timeout_is_enforced(self):
        import subprocess,sys
        real_run=subprocess.run
        def slow_child(command,**kwargs):
            return real_run([sys.executable,"-c","import time; time.sleep(10)"],**kwargs)
        source=Path(self.folder.name)/self.op.version.original_storage_key
        with override_settings(DOCUMENTS_TIMEOUT_SECONDS=0.05), patch("apps.documents.worker.subprocess.run",side_effect=slow_child):
            with self.assertRaises(ExtractionError) as raised:
                run_parser(source,self.op.version)
        self.assertEqual(raised.exception.code,"TIMEOUT")
