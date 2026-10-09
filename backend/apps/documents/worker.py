"""Durable W2 queue. Run separately from the HTTP process."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import IngestionJob, DocumentVersion, KnowledgeDocument
from .storage import private_path
from .processors.parser import ExtractionError, ExtractionResult, ExtractedPage
from .processors.metadata import write_extraction


def run_watermark(source,version,destination,timeout):
    environment=os.environ.copy()
    environment["PYTHONPATH"]=os.pathsep.join(str(p) for p in sys.path if p)
    try:
        completed=subprocess.run([sys.executable,"-m","apps.documents.processors.watermark_child",str(source),str(destination),
            str(version.document_id),str(version.version_number)],env=environment,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,timeout=timeout,check=False)
        if completed.returncode or not destination.is_file():
            raise ExtractionError("WATERMARK_FAILED","Protected view could not be created.")
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError("TIMEOUT","Protected view exceeded processing deadline.") from exc


def lock_document_for_job(job_id):
    document_id = IngestionJob.objects.values_list("document_version__document_id", flat=True).get(pk=job_id)
    return KnowledgeDocument.objects.select_for_update().get(pk=document_id)


def recover_expired_jobs():
    count = 0
    candidates = list(IngestionJob.objects.filter(status="RUNNING", lease_expires_at__lt=timezone.now()).values_list("pk",flat=True))
    for job_id in candidates:
        with transaction.atomic():
            lock_document_for_job(job_id)
            job = IngestionJob.objects.select_for_update().get(pk=job_id)
            if job.status != "RUNNING" or job.lease_expires_at >= timezone.now(): continue
            job.status = "FAILED"; job.error_code = "WORKER_INTERRUPTED"
            job.worker_token = None; job.finished_at = timezone.now()
            job.save(update_fields=["status", "error_code", "worker_token", "finished_at"])
            DocumentVersion.objects.filter(pk=job.document_version_id, status="PROCESSING", removed_at__isnull=True).update(status="FAILED")
            count += 1
    return count


def claim_job():
    recover_expired_jobs()
    for job_id in IngestionJob.objects.filter(status="QUEUED").order_by("created_at").values_list("pk", flat=True)[:20]:
        with transaction.atomic():
            lock_document_for_job(job_id)
            now = timezone.now(); token = uuid.uuid4()
            updated = IngestionJob.objects.filter(pk=job_id, status="QUEUED",
                document_version__removed_at__isnull=True,
                document_version__document__removed_at__isnull=True).update(status="RUNNING", worker_token=token,
                started_at=now, lease_expires_at=now+timedelta(seconds=getattr(settings,"DOCUMENTS_TIMEOUT_SECONDS",900)+60),
                attempt_count=F("attempt_count")+1, error_code="")
            if updated:
                job = IngestionJob.objects.select_related("document_version__document").get(pk=job_id)
                DocumentVersion.objects.filter(pk=job.document_version_id, removed_at__isnull=True).update(status="PROCESSING")
                return job
    return None


def run_parser(source, version):
    # Child has no database access; subprocess timeout terminates conversion.
    folder = private_path("worker-temp"); folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as task_dir:
        output = Path(task_dir)/"result.json"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(str(p) for p in sys.path if p)
        command = [sys.executable, "-m", "apps.documents.processors.worker_child", str(source), str(output),
            str(getattr(settings,"DOCUMENTS_MAX_PAGES",100)), str(getattr(settings,"DOCUMENTS_MAX_BYTES",20*1024*1024))]
        try:
            with (Path(task_dir)/"conversion.log").open("wb") as log:
                completed = subprocess.run(command, stdout=log, stderr=log, env=environment,
                    timeout=getattr(settings,"DOCUMENTS_TIMEOUT_SECONDS",900), check=False)
        except subprocess.TimeoutExpired as exc:
            raise ExtractionError("TIMEOUT", "Extraction timed out.") from exc
        if not output.exists():
            raise ExtractionError("CONVERSION_FAILED", "Extraction failed.")
        payload = json.loads(output.read_text(encoding="utf-8"))
        if payload.get("error_code"):
            raise ExtractionError(payload["error_code"], "Extraction failed.")
        if completed.returncode:
            raise ExtractionError("CONVERSION_FAILED", "Extraction failed.")
        return ExtractionResult(page_count=payload["page_count"],
            pages=tuple(ExtractedPage(**page) for page in payload["pages"]),
            parser_version=payload["parser_version"],checksum_sha256=payload["checksum_sha256"],ocr_enabled=payload["ocr_enabled"])


def process_job(job, runner=None):
    token = job.worker_token
    candidate = None
    watermarked = None
    started=time.monotonic()
    try:
        if not IngestionJob.objects.filter(pk=job.pk,status="RUNNING",worker_token=token).exists(): return
        version = DocumentVersion.objects.select_related("document").get(pk=job.document_version_id)
        source = private_path(version.original_storage_key)
        if hashlib.sha256(source.read_bytes()).hexdigest() != version.checksum_sha256:
            raise ExtractionError("SOURCE_CHANGED", "Source changed.")
        result = (runner or run_parser)(source, version)
        if result.checksum_sha256 != version.checksum_sha256 or hashlib.sha256(source.read_bytes()).hexdigest() != version.checksum_sha256:
            raise ExtractionError("SOURCE_CHANGED", "Source changed.")
        if result.page_count != version.page_count or [p.page_number for p in result.pages] != list(range(1,version.page_count+1)):
            raise ExtractionError("INCOMPLETE_CONVERSION", "Extraction missing pages.")
        key = f"extracted/{version.pk}/{token}.json"
        candidate = private_path(key)
        write_extraction(result, {"course_id":version.document.course_id,"document_id":version.document_id,"version_id":version.pk}, candidate)
        watermark_key=f"views/{version.pk}/{token}.pdf"
        watermarked=private_path(watermark_key)
        remaining=getattr(settings,"DOCUMENTS_TIMEOUT_SECONDS",900)-(time.monotonic()-started)
        if remaining<=0:raise ExtractionError("TIMEOUT","Processing deadline exceeded.")
        run_watermark(source,version,watermarked,remaining)
        from pypdf import PdfReader
        if len(PdfReader(watermarked).pages)!=version.page_count:
            raise ExtractionError("WATERMARK_FAILED","Protected view page count mismatch.")
        if hashlib.sha256(source.read_bytes()).hexdigest()!=version.checksum_sha256:
            raise ExtractionError("SOURCE_CHANGED","Source changed.")
        watermark_digest=hashlib.sha256(watermarked.read_bytes()).hexdigest()
        with transaction.atomic():
            # Serialize document mutations with removal and retry.
            lock_document_for_job(job.pk)
            locked_version = DocumentVersion.objects.select_for_update().get(pk=version.pk)
            locked_job = IngestionJob.objects.select_for_update().get(pk=job.pk)
            if (locked_job.status != "RUNNING" or locked_job.worker_token != token or
                locked_version.removed_at or locked_version.document.removed_at or locked_version.status != "PROCESSING"):
                candidate.unlink(missing_ok=True);watermarked.unlink(missing_ok=True); return
            locked_version.status="EXTRACTED";locked_version.extracted_storage_key=key
            locked_version.extracted_at=timezone.now();locked_version.indexed_at=None
            locked_version.watermarked_view_key=watermark_key;locked_version.watermark_status="READY"
            locked_version.watermarked_sha256=watermark_digest
            locked_version.save(update_fields=["status","extracted_storage_key","extracted_at","indexed_at","watermarked_view_key","watermark_status","watermarked_sha256"])
            locked_job.status="SUCCEEDED";locked_job.finished_at=timezone.now();locked_job.worker_token=None
            locked_job.save(update_fields=["status","finished_at","worker_token"])
    except Exception as exc:
        code = exc.code if isinstance(exc, ExtractionError) else "CONVERSION_FAILED"
        with transaction.atomic():
            lock_document_for_job(job.pk)
            locked_version = DocumentVersion.objects.select_for_update().get(pk=job.document_version_id)
            updated = IngestionJob.objects.filter(pk=job.pk,status="RUNNING",worker_token=token).update(
                status="FAILED",error_code=code,finished_at=timezone.now(),worker_token=None)
            if updated and not locked_version.removed_at:
                locked_version.status="FAILED";locked_version.watermark_status="FAILED"
                locked_version.save(update_fields=["status","watermark_status"])
        if candidate: candidate.unlink(missing_ok=True)
        if watermarked:watermarked.unlink(missing_ok=True)
