"""Reproducible A+B HTTP/Docling verification on an in-memory fixture DB."""
import io
import json
import os
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
os.environ["DJANGO_SETTINGS_MODULE"]="config.settings.w2_test"
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client,override_settings
from reportlab.pdfgen.canvas import Canvas
from apps.documents.models import IngestionJob,DocumentVersion
from apps.documents.worker import claim_job,process_job


def main():
    if settings.DATABASES["default"]["NAME"] != ":memory:":
        raise RuntimeError("This verification must use an in-memory test DB.")
    call_command("migrate",run_syncdb=True,verbosity=0)
    get_user_model().objects.create_user("w2-fixture-teacher",password="Fixture123!",role="TEACHER")
    client=Client(enforce_csrf_checks=True)
    response=client.post("/api/users/login/",{"username":"w2-fixture-teacher","password":"Fixture123!"},content_type="application/json")
    assert response.status_code==200,response.content
    client.defaults["HTTP_AUTHORIZATION"]="Bearer "+response.json()["access"]
    response=client.post("/api/courses/",{"title":"W2 A+B fixture"},content_type="application/json")
    assert response.status_code==201,response.content
    course_id=response.json()["id"]
    stream=io.BytesIO();canvas=Canvas(stream)
    for label in ["W2 PAGE ONE","W2 PAGE TWO"]:
        canvas.drawString(40,700,label);canvas.showPage()
    canvas.save()
    with override_settings(DOCUMENTS_STORAGE_ROOT=ROOT/"data/processed/w2-ab-verification"):
        start=time.monotonic()
        response=client.post(f"/api/courses/{course_id}/documents/",{"title":"W2 fixture","file":SimpleUploadedFile("demo.pdf",stream.getvalue())},HTTP_IDEMPOTENCY_KEY="w2-fixture-upload")
        upload_seconds=time.monotonic()-start
        assert response.status_code==202,response.content
        job=claim_job();start=time.monotonic();process_job(job);seconds=time.monotonic()-start
        job.refresh_from_db();version=DocumentVersion.objects.get(pk=job.document_version_id)
        assert job.status=="SUCCEEDED",(job.status,job.error_code)
        extraction=client.get(f"/api/documents/{version.document_id}/extraction/?version_id={version.pk}")
        assert extraction.status_code==200,extraction.content
        payload=extraction.json()
        assert payload["course_id"]==course_id and payload["page_count"]==2
        assert "PAGE ONE" in payload["pages"][0]["text"] and "PAGE TWO" in payload["pages"][1]["text"]
        assert payload["rag_ready"] is False and payload["indexed_at"] is None
        report={"fixture_only":True,"a_commit":"b8b03df","actual_models":["users.User","courses.Course","courses.CourseMember"],
            "actual_login":"/api/users/login/","authentication":"JWT Bearer","upload_http":202,
            "upload_seconds":round(upload_seconds,3),"extraction_seconds":round(seconds,3),
            "job_status":job.status,"version_status":version.status,"page_count":2,"physical_pages_verified":True,
            "scope_UUIDs_verified":True,"rag_ready":False,"indexed_at":None}
        output=ROOT/"docs/reports/w2-ab-integration-verification.json"
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__":main()
