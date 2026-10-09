import io
import json
import tempfile
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase,Client,override_settings
from rest_framework_simplejwt.tokens import RefreshToken
from reportlab.pdfgen.canvas import Canvas
from tests.document_support.models import Course,Membership
from apps.documents.models import KnowledgeDocument,DocumentVersion,IngestionJob,DocumentOperation

class UploadTests(TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.storage=override_settings(DOCUMENTS_STORAGE_ROOT=Path(self.folder.name));self.storage.enable();self.addCleanup(self.storage.disable)
        User=get_user_model()
        self.teacher=User.objects.create_user(username="teacher",password="test")
        self.other=User.objects.create_user(username="other",password="test")
        self.student=User.objects.create_user(username="student",password="test")
        self.course=Course.objects.create(teacher=self.teacher,title="Course")
        Membership.objects.create(course=self.course,user=self.student)
        self.url=f"/api/courses/{self.course.pk}/documents/"
        self.client=Client(enforce_csrf_checks=True)
        self.authenticate(self.teacher)
    def authenticate(self,user):
        self.client.defaults["HTTP_AUTHORIZATION"]="Bearer "+str(RefreshToken.for_user(user).access_token)
    def pdf(self,text="TEST PAGE"):
        stream=io.BytesIO();c=Canvas(stream);c.drawString(30,700,text);c.showPage();c.save()
        return SimpleUploadedFile("sample.pdf",stream.getvalue(),content_type="application/pdf")
    def upload(self,key="upload-1",**kwargs):
        return self.client.post(self.url,{"title":"Document","file":self.pdf()},HTTP_IDEMPOTENCY_KEY=key,**kwargs)
    def test_upload_is_private_and_queued_without_conversion(self):
        with patch("apps.documents.processors.parser.extract_pdf") as parser:
            response=self.upload();parser.assert_not_called()
        self.assertEqual(response.status_code,202,response.content)
        self.assertEqual(KnowledgeDocument.objects.count(),1)
        document=KnowledgeDocument.objects.get();version=DocumentVersion.objects.get();job=IngestionJob.objects.get()
        self.assertEqual(document.material_policy,"PROTECTED")
        self.assertEqual(job.status,"QUEUED")
        self.assertTrue((Path(self.folder.name)/version.original_storage_key).is_file())
        self.assertNotIn("storage_key",response.content.decode())
        self.assertIsNone(version.indexed_at)
    def test_bearer_upload_does_not_require_csrf(self):
        response=self.client.post(self.url,{"title":"Doc","file":self.pdf()},HTTP_IDEMPOTENCY_KEY="bearer")
        self.assertEqual(response.status_code,202,response.content)
    def test_session_alone_is_not_accepted(self):
        self.client.defaults.pop("HTTP_AUTHORIZATION")
        self.client.force_login(self.teacher)
        self.assertEqual(self.upload().status_code,401)
    def test_invalid_jwt_is_denied(self):
        self.client.defaults["HTTP_AUTHORIZATION"]="Bearer invalid"
        self.assertEqual(self.upload().status_code,401)
    def test_expired_access_token_is_denied(self):
        token=RefreshToken.for_user(self.teacher).access_token
        token.set_exp(lifetime=timedelta(seconds=-1))
        self.client.defaults["HTTP_AUTHORIZATION"]="Bearer "+str(token)
        self.assertEqual(self.upload().status_code,401)
    def test_refresh_token_is_not_an_access_token(self):
        self.client.defaults["HTTP_AUTHORIZATION"]="Bearer "+str(RefreshToken.for_user(self.teacher))
        self.assertEqual(self.upload().status_code,401)
    def test_missing_token_is_denied(self):
        self.client.defaults.pop("HTTP_AUTHORIZATION")
        self.assertEqual(self.upload().status_code,401)
    def test_inactive_user_is_denied_even_with_previously_valid_token(self):
        self.teacher.status="BLOCKED";self.teacher.save(update_fields=["status"])
        self.assertEqual(self.upload().status_code,401)
    def test_student_and_other_teacher_cannot_upload(self):
        for user in [self.student,self.other]:
            self.authenticate(user)
            self.assertEqual(self.upload().status_code,404)
        self.assertEqual(KnowledgeDocument.objects.count(),0)
    def test_idempotent_upload_returns_same_document(self):
        # Reuse exact bytes; reportlab PDFs may embed random identifiers.
        pdf=self.pdf();data=pdf.read()
        def post():return self.client.post(self.url,{"title":"Doc","file":SimpleUploadedFile("same.pdf",data)},HTTP_IDEMPOTENCY_KEY="repeat")
        first=post();second=post()
        self.assertEqual(first.status_code,202,first.content);self.assertEqual(second.status_code,202,second.content)
        self.assertEqual(first.json()["document_id"],second.json()["document_id"])
        self.assertEqual(DocumentVersion.objects.count(),1);self.assertEqual(IngestionJob.objects.count(),1)
    def test_key_reuse_with_different_payload_is_conflict(self):
        self.assertEqual(self.upload().status_code,202)
        response=self.client.post(self.url,{"title":"Changed","file":self.pdf("DIFFERENT")},HTTP_IDEMPOTENCY_KEY="upload-1")
        self.assertEqual(response.status_code,409)
        self.assertEqual(KnowledgeDocument.objects.count(),1)
    def test_invalid_pdf_rejected_and_no_orphan_files(self):
        response=self.client.post(self.url,{"file":SimpleUploadedFile("fake.pdf",b"fake")},HTTP_IDEMPOTENCY_KEY="fake")
        self.assertEqual(response.status_code,415)
        self.assertEqual(DocumentVersion.objects.count(),0)
        self.assertEqual([p for p in Path(self.folder.name).rglob("*") if p.is_file()],[])
    def test_status_checks_membership_and_never_exposes_original(self):
        response=self.upload();self.assertEqual(response.status_code,202,response.content)
        url=f"/api/documents/{response.json()['document_id']}/status/"
        KnowledgeDocument.objects.filter(pk=response.json()['document_id']).update(is_published=True,published_version_id=response.json()["version_id"])
        self.authenticate(self.student)
        self.assertEqual(self.client.get(url).status_code,200)
        Membership.objects.filter(user=self.student).update(active=False)
        self.assertEqual(self.client.get(url).status_code,404)
    def test_no_basic_auth_fallback(self):
        self.assertEqual(self.client.post(self.url,{"file":self.pdf()},HTTP_AUTHORIZATION="Basic dGVhY2hlcjp0ZXN0").status_code,401)
    @override_settings(DOCUMENTS_MAX_BYTES=10)
    def test_size_limit_leaves_no_rows_or_files(self):
        self.assertEqual(self.upload().status_code,413)
        self.assertEqual(DocumentVersion.objects.count(),0)
        self.assertFalse(any(p.is_file() for p in Path(self.folder.name).rglob("*")))
    @override_settings(DOCUMENTS_MAX_PAGES=0)
    def test_page_limit_rejected(self):
        self.assertEqual(self.upload().status_code,400)
        self.assertEqual(DocumentVersion.objects.count(),0)
    def test_encrypted_pdf_rejected(self):
        from pypdf import PdfWriter
        buf=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.encrypt("secret");writer.write(buf)
        response=self.client.post(self.url,{"file":SimpleUploadedFile("encrypted.pdf",buf.getvalue())},HTTP_IDEMPOTENCY_KEY="encrypted")
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.json()["error"]["code"],"ENCRYPTED_PDF")
    def test_student_cannot_read_draft_or_extraction(self):
        response=self.upload();document_id=response.json()["document_id"]
        self.authenticate(self.student)
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/status/").status_code,404)
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/extraction/").status_code,404)
    def test_delete_cancels_job_and_idempotent_upload_does_not_revive(self):
        pdf=self.pdf().read()
        def post():return self.client.post(self.url,{"title":"Doc","file":SimpleUploadedFile("same.pdf",pdf)},HTTP_IDEMPOTENCY_KEY="repeat")
        response=post();document_id=response.json()["document_id"]
        self.assertEqual(self.client.delete(f"/api/documents/{document_id}/").status_code,204)
        self.assertEqual(IngestionJob.objects.get().status,"CANCELLED")
        self.assertEqual(post().status_code,404)
    def test_original_download_route_is_not_exposed(self):
        response=self.upload();document_id=response.json()["document_id"]
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/download/").status_code,403)
