"""W2 evidence on a disposable SQLite DB, with real corpus and separate workers.

Never seeds the application DB. No credentials or full extracted text in report.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Must be invoked before Django is configured; force a fresh private sandbox.
    if "django.conf" in sys.modules:
        raise RuntimeError("Run this verification in a fresh Python process.")
    parent = ROOT / "data/processed"
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="w2-delivery-", dir=parent) as folder:
        database = Path(folder) / "verification.sqlite3"
        storage = Path(folder) / "private"
        os.environ.update(DJANGO_SETTINGS_MODULE="config.settings.w2",
                          DB_ENGINE="django.db.backends.sqlite3", DB_NAME=str(database),
                          DOCUMENTS_STORAGE_ROOT=str(storage))
        sys.path.insert(0, str(ROOT / "backend"))
        import django
        django.setup()
        from django.conf import settings
        from django.contrib.auth import get_user_model
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.core.management import call_command
        from django.db import connections
        from django.test import Client
        from django.utils import timezone
        from datetime import timedelta
        from pypdf import PdfWriter
        from apps.documents.models import IngestionJob, KnowledgeDocument
        from apps.courses.models import CourseMember
        from apps.documents.worker import claim_job, recover_expired_jobs

        assert Path(settings.DATABASES['default']['NAME']).resolve() == database.resolve()
        call_command("migrate", verbosity=0)
        User = get_user_model()
        password = secrets.token_urlsafe(28)
        User.objects.create_user("w2-delivery-teacher", password=password, role="TEACHER")
        student = User.objects.create_user("w2-delivery-student", password=password)
        client = Client()

        def login(username):
            client.defaults.pop("HTTP_AUTHORIZATION", None)
            response = client.post("/api/users/login/", {"username": username, "password": password}, content_type="application/json")
            assert response.status_code == 200
            client.defaults["HTTP_AUTHORIZATION"] = "Bearer " + response.json()["access"]

        def post_json(url, payload):
            return client.post(url, payload, content_type="application/json")

        login("w2-delivery-teacher")
        records = []
        for subject in ("KTCTMLN", "CNXHKH"):
            response = post_json("/api/courses/", {"title": "W2 fixture " + subject})
            assert response.status_code == 201, response.content
            course_id = response.json()["id"]
            response = client.patch(f"/api/courses/{course_id}/", {"status": "PUBLISHED"}, content_type="application/json")
            assert response.status_code == 200
            created_class = post_json(f"/api/courses/{course_id}/classrooms/", {"name": "Delivery class"})
            assert created_class.status_code == 201
            classroom = client.get(f"/api/courses/{course_id}/classrooms/")
            assert classroom.status_code == 200
            class_code = classroom.json()["results"][0]["class_code"]
            login("w2-delivery-student")
            joined = post_json("/api/courses/join/", {"class_code": class_code})
            assert joined.status_code == 201
            assert joined.json()["status"] == "ENROLLED"
            login("w2-delivery-teacher")
            member_id = str(CourseMember.objects.get(course_id=course_id, user=student).pk)
            source = ROOT / "data/corpus" / subject / "ch01.pdf"
            data = source.read_bytes()
            started = time.monotonic()
            response = client.post(f"/api/courses/{course_id}/documents/",
                {"title": subject + " chương 1", "file": SimpleUploadedFile("ch01.pdf", data)},
                HTTP_IDEMPOTENCY_KEY=subject)
            assert response.status_code == 202, response.content
            records.append({"subject": subject, "course_id": course_id,
                "member_id": member_id, **response.json(),
                "checksum_sha256": hashlib.sha256(data).hexdigest(),
                "upload_seconds": round(time.monotonic() - started, 3)})

        # Simulate a claimed job whose worker disappeared; recover and retry via API.
        interrupted = claim_job()
        IngestionJob.objects.filter(pk=interrupted.pk).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
        assert recover_expired_jobs() == 1
        url = f"/api/documents/{interrupted.document_version.document_id}/retry/"
        body = {"version_id": str(interrupted.document_version_id)}
        first = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="restart-retry")
        second = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="restart-retry")
        assert first.status_code == second.status_code == 202
        assert first.json()["job_id"] == second.json()["job_id"]

        # A structurally valid PDF containing an image but no text requires OCR.
        from PIL import Image
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.utils import ImageReader
        stream = io.BytesIO()
        canvas = Canvas(stream)
        canvas.drawImage(ImageReader(Image.new("RGB", (50,50), "black")), 20,20,100,100)
        canvas.showPage(); canvas.save()
        failed = client.post(f"/api/courses/{records[0]['course_id']}/documents/",
            {"title":"OCR fixture", "file":SimpleUploadedFile("needs-ocr.pdf", stream.getvalue())},
            HTTP_IDEMPOTENCY_KEY="needs-ocr")
        assert failed.status_code == 202

        # Three new worker processes read the durable queue from disk.
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(str(p) for p in sys.path if p)
        command = [sys.executable, str(ROOT/"backend/manage.py"), "run_ingestion_worker", "--once", "--settings=config.settings.w2"]
        connections.close_all()
        worker_seconds = []
        for _ in range(3):
            started = time.monotonic()
            result = subprocess.run(command, env=environment, capture_output=True, timeout=960)
            assert result.returncode == 0, "Separate worker failed; inspect local runtime."
            worker_seconds.append(round(time.monotonic()-started,3))
        connections.close_all()

        for record in records:
            url = f"/api/documents/{record['document_id']}/extraction/?version_id={record['version_id']}"
            response = client.get(url)
            assert response.status_code == 200, response.content
            payload = response.json()
            assert payload["checksum_sha256"] == record["checksum_sha256"]
            assert payload["course_id"] == record["course_id"]
            assert [p["page_number"] for p in payload["pages"]] == list(range(1,payload["page_count"]+1))
            assert payload["rag_ready"] is False and payload["indexed_at"] is None
            record.update(page_count=payload["page_count"], parser_version=payload["parser"]["version"],
                          extraction_status="EXTRACTED", physical_pages_verified=True)
        failed_job = IngestionJob.objects.get(pk=failed.json()["job_id"])
        assert failed_job.status == "FAILED" and failed_job.error_code == "OCR_REQUIRED"

        # Real publication/view/policy APIs; no direct database publication fixture.
        document_id = records[0]["document_id"]
        login("w2-delivery-student")
        assert client.get(f"/api/documents/{document_id}/status/").status_code == 404
        login("w2-delivery-teacher")
        published=client.patch(f"/api/documents/{document_id}/publication/",{"is_published":True,"version_id":records[0]["version_id"]},content_type="application/json")
        assert published.status_code==200,published.content
        login("w2-delivery-student")
        assert client.get(f"/api/documents/{document_id}/status/").status_code == 200
        view=client.get(f"/api/documents/{document_id}/view/")
        assert view.status_code==200 and view["Cache-Control"]=="private, no-store"
        from pypdf import PdfReader
        assert "OHAYO" in PdfReader(io.BytesIO(view.content)).pages[0].extract_text()
        assert client.get(f"/api/documents/{document_id}/download/").status_code==403
        login("w2-delivery-teacher")
        changed=client.patch(f"/api/documents/{document_id}/policy/",{"material_policy":"PUBLIC_DOWNLOAD","policy_revision":1},content_type="application/json")
        assert changed.status_code==200
        login("w2-delivery-student")
        download=client.get(f"/api/documents/{document_id}/download/")
        assert download.status_code==200
        assert hashlib.sha256(download.content).hexdigest()==records[0]["checksum_sha256"]
        login("w2-delivery-teacher")
        changed=client.patch(f"/api/documents/{document_id}/policy/",{"material_policy":"PROTECTED","policy_revision":2},content_type="application/json")
        assert changed.status_code==200
        login("w2-delivery-student")
        assert client.get(f"/api/documents/{document_id}/download/").status_code==403
        assert client.get(f"/api/documents/{document_id}/extraction/").status_code == 404
        login("w2-delivery-teacher")
        assert client.delete(f"/api/courses/{records[0]['course_id']}/members/{records[0]['member_id']}/").status_code == 204
        login("w2-delivery-student")
        assert client.get(f"/api/documents/{document_id}/status/").status_code == 404
        connections.close_all()
        report = {"verified_at": timezone.now().isoformat(), "fixture_only": True,
            "database": "disposable SQLite, fresh migrations, separate worker processes",
            "sources": records, "worker_process_seconds": worker_seconds,
            "restart_recovery": "WORKER_INTERRUPTED -> API retry -> EXTRACTED",
            "retry_idempotent": True, "failed_pdf": {"job_status":"FAILED","error_code":"OCR_REQUIRED"},
            "membership_revocation_checked": True, "publication_fixture_only": False,
            "viewer_watermark_implemented": True, "policy_roundtrip_checked":True,"rag_ready": False,
            "postgresql_verified": False, "browser_demo_recorded": False}
        output = ROOT/"docs/reports/w2-delivery-verification.json"
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False))


if __name__ == "__main__":
    main()
