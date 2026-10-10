import hashlib
import io
from unittest.mock import patch
from pypdf import PdfReader
from apps.documents.models import DocumentVersion
from apps.documents.storage import private_path
from apps.documents.worker import claim_job, process_job
from apps.documents.processors.parser import ExtractionResult, ExtractedPage
from django.test import TestCase
from tests.documents import test_integration as integration


class MaterialAccessTests(TestCase):
    setUp=integration.AIntegrationTests.setUp
    login=integration.AIntegrationTests.login
    upload=integration.AIntegrationTests.upload
    upload_file=integration.AIntegrationTests.upload_file
    def test_rename_requires_owner_and_changes_only_document_title(self):
        from apps.documents.models import KnowledgeDocument
        uploaded=self.upload().json()
        base=f"/api/documents/{uploaded['document_id']}/"
        response=self.client.patch(base,{"title":"  Tên mới  "},content_type="application/json")
        self.assertEqual(response.status_code,200,response.content)
        document=KnowledgeDocument.objects.get(pk=uploaded['document_id'])
        self.assertEqual(document.title,"Tên mới")
        self.assertEqual(document.versions.count(),1)
        self.assertEqual(self.client.get(self.url).json()['results'][0]['title'],'Tên mới')
        for value in ['', '   ', 'x'*256, None, 123]:
            self.assertEqual(self.client.patch(base,{"title":value},content_type="application/json").status_code,400)
        self.assertEqual(self.client.patch(base,{"title":"Changed","is_published":True},content_type="application/json").status_code,400)
        for username,password in [('student','Student123!'),('other','Teacher123!')]:
            self.login(username,password)
            self.assertEqual(self.client.patch(base,{"title":"Unauthorized"},content_type="application/json").status_code,404)
        document.refresh_from_db()
        self.assertEqual(document.title,'Tên mới')
    # Reuse real A login/course/class enrollment setup, without inheriting tests twice.
    def prepare(self):
        uploaded=self.upload().json()
        job=claim_job()
        process_job(job,runner=lambda source,version: ExtractionResult(1,(ExtractedPage(1,"PAGE ONE","OK"),),"test",version.checksum_sha256))
        self.version=DocumentVersion.objects.get(pk=uploaded["version_id"])
        self.document_id=uploaded["document_id"]
        self.base=f"/api/documents/{self.document_id}/"
        return uploaded

    def publish(self):
        return self.client.patch(self.base+"publication/",{"is_published":True,"version_id":str(self.version.pk)},content_type="application/json")

    def policy(self,value,revision=1):
        return self.client.patch(self.base+"policy/",{"material_policy":value,"policy_revision":revision},content_type="application/json")

    def test_worker_creates_watermark_without_changing_original_or_extraction(self):
        self.prepare()
        self.assertEqual(self.version.watermark_status,"READY")
        original=private_path(self.version.original_storage_key).read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(),self.version.checksum_sha256)
        view=PdfReader(private_path(self.version.watermarked_view_key))
        self.assertEqual(len(view.pages),1)
        self.assertIn("OHAYO",view.pages[0].extract_text())
        extraction=self.client.get(self.base+"extraction/").json()
        self.assertNotIn("OHAYO",extraction["pages"][0]["text"])

    def test_publication_protected_view_and_public_download_policy_reversal(self):
        self.prepare();self.assertEqual(self.publish().status_code,200)
        self.login("student","Student123!")
        response=self.client.get(self.base+"view/");self.assertEqual(response.status_code,200)
        self.assertIn("OHAYO",PdfReader(io.BytesIO(response.content)).pages[0].extract_text())
        self.assertEqual(response["Cache-Control"],"private, no-store")
        self.assertEqual(self.client.get(self.base+"download/").status_code,403)
        self.login("teacher","Teacher123!")
        self.assertEqual(self.policy("PUBLIC_DOWNLOAD").status_code,200)
        self.assertEqual(self.policy("PROTECTED",1).status_code,409)
        self.login("student","Student123!")
        response=self.client.get(self.base+"download/");self.assertEqual(response.status_code,200)
        self.assertEqual(hashlib.sha256(response.content).hexdigest(),self.version.checksum_sha256)
        self.assertNotIn("OHAYO",PdfReader(io.BytesIO(self.client.get(self.base+"view/").content)).pages[0].extract_text())
        self.login("teacher","Teacher123!")
        self.assertEqual(self.policy("PROTECTED",2).status_code,200)
        self.login("student","Student123!")
        self.assertEqual(self.client.get(self.base+"download/").status_code,403)

    def test_unpublish_and_membership_revoke_block_view_content(self):
        self.prepare();self.assertEqual(self.publish().status_code,200)
        self.login("student","Student123!");self.assertEqual(self.client.get(self.base+"view/").status_code,200)
        self.login("teacher","Teacher123!")
        self.assertEqual(self.client.patch(self.base+"publication/",{"is_published":False},content_type="application/json").status_code,200)
        self.login("student","Student123!");self.assertEqual(self.client.get(self.base+"view/").status_code,404)
        self.login("teacher","Teacher123!");self.assertEqual(self.publish().status_code,200)
        self.assertEqual(self.client.delete(f"/api/courses/{self.course_id}/members/{self.member_id}/").status_code,204)
        self.login("student","Student123!");self.assertEqual(self.client.get(self.base+"view/").status_code,404)

    def test_replacement_keeps_old_published_version_until_teacher_publishes_new(self):
        self.prepare();self.assertEqual(self.publish().status_code,200)
        original_view=self.client.get(self.base+"view/").content
        response=self.client.post(self.base+"versions/",{"file":self.upload_file()},HTTP_IDEMPOTENCY_KEY="new-version")
        self.assertEqual(response.status_code,202);new_id=response.json()["version_id"]
        self.assertEqual(self.client.get(self.base+"view/").content,original_view)
        self.assertEqual(self.client.patch(self.base+"publication/",{"is_published":True,"version_id":new_id},content_type="application/json").status_code,409)
        self.login("student","Student123!")
        self.assertEqual(self.client.get(self.url).json()["results"][0]["version_id"],str(self.version.pk))
        self.assertEqual(self.client.get(self.base+f"status/?version_id={new_id}").status_code,404)

    def test_failed_or_missing_watermark_never_falls_back_to_original(self):
        self.prepare();self.assertEqual(self.publish().status_code,200)
        private_path(self.version.watermarked_view_key).unlink()
        self.assertEqual(self.client.get(self.base+"view/").status_code,503)
        self.assertEqual(self.client.get(self.base+"status/").json()["watermark_status"],"FAILED")
        self.assertEqual(self.client.get(self.url).json()["results"][0]["watermark_status"],"FAILED")
        response=self.client.post(self.base+"retry/",{"version_id":str(self.version.pk)},content_type="application/json",HTTP_IDEMPOTENCY_KEY="missing-view")
        self.assertEqual(response.status_code,202)

    def test_other_teacher_cannot_publish_or_change_policy(self):
        self.prepare();self.login("other","Teacher123!")
        self.assertEqual(self.publish().status_code,404)
        self.assertEqual(self.policy("PUBLIC_DOWNLOAD").status_code,404)

    def test_watermark_failure_is_retryable_and_does_not_publish_clean_source(self):
        uploaded=self.upload().json();self.document_id=uploaded["document_id"];self.base=f"/api/documents/{self.document_id}/"
        job=claim_job()
        from apps.documents.processors.parser import ExtractionError
        with patch("apps.documents.worker.run_watermark",side_effect=ExtractionError("WATERMARK_FAILED","Unavailable")):
            process_job(job,runner=lambda source,version:ExtractionResult(1,(ExtractedPage(1,"PAGE ONE","OK"),),"test",version.checksum_sha256))
        self.version=DocumentVersion.objects.get(pk=uploaded["version_id"])
        self.assertEqual(self.version.status,"FAILED");self.assertEqual(self.version.watermark_status,"FAILED")
        self.assertEqual(self.publish().status_code,409)
        self.assertEqual(self.client.get(self.base+"view/").status_code,409)
        response=self.client.post(self.base+"retry/",{"version_id":str(self.version.pk)},content_type="application/json",HTTP_IDEMPOTENCY_KEY="watermark-retry")
        self.assertEqual(response.status_code,202)

    def test_legacy_extracted_version_can_prepare_protected_view(self):
        uploaded=self.upload().json()
        version=DocumentVersion.objects.get(pk=uploaded["version_id"])
        version.jobs.update(status="SUCCEEDED")
        version.status="EXTRACTED";version.save(update_fields=["status"])
        response=self.client.post(f"/api/documents/{version.document_id}/retry/",{"version_id":str(version.pk)},content_type="application/json",HTTP_IDEMPOTENCY_KEY="legacy-view")
        self.assertEqual(response.status_code,202)

    def test_teacher_can_preview_replacement_without_exposing_it_to_student(self):
        self.prepare()
        first = self.version
        self.assertEqual(self.publish().status_code, 200)
        response = self.client.post(self.base+'versions/', {'file': self.upload_file()}, HTTP_IDEMPOTENCY_KEY='preview-replacement')
        new_id = response.json()['version_id']
        process_job(claim_job(), runner=lambda source,version: ExtractionResult(1,(ExtractedPage(1,'REPLACEMENT','OK'),),'test',version.checksum_sha256))
        replacement = DocumentVersion.objects.get(pk=new_id)
        teacher = self.client.get(self.base+f'view/?version_id={new_id}', HTTP_ACCEPT='application/pdf, application/json')
        self.assertEqual(teacher.status_code, 200)
        self.assertEqual(hashlib.sha256(teacher.content).hexdigest(), replacement.watermarked_sha256)
        self.login('student','Student123!')
        student = self.client.get(self.base+f'view/?version_id={new_id}')
        self.assertEqual(student.status_code, 200)
        self.assertEqual(hashlib.sha256(student.content).hexdigest(), first.watermarked_sha256)

    def test_teacher_downloads_protected_original_before_processing(self):
        uploaded = self.upload().json()
        version = DocumentVersion.objects.get(pk=uploaded['version_id'])
        response = self.client.get(f"/api/documents/{uploaded['document_id']}/download/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(hashlib.sha256(response.content).hexdigest(), version.checksum_sha256)
        self.assertIn('attachment', response['Content-Disposition'])
        self.login('student', 'Student123!')
        self.assertEqual(self.client.get(f"/api/documents/{uploaded['document_id']}/download/").status_code, 404)

    def test_teacher_downloads_latest_replacement_student_only_published(self):
        self.prepare()
        self.assertEqual(self.publish().status_code, 200)
        self.assertEqual(self.policy('PUBLIC_DOWNLOAD').status_code, 200)
        response = self.client.post(self.base+'versions/', {'file': self.upload_file()}, HTTP_IDEMPOTENCY_KEY='download-replacement')
        new_id = response.json()['version_id']
        teacher = self.client.get(self.base+'download/')
        self.assertEqual(teacher.status_code, 200, teacher.content)
        self.assertEqual(teacher['X-Document-Version'], new_id)
        self.login('student', 'Student123!')
        student = self.client.get(self.base+f'download/?version_id={new_id}')
        self.assertEqual(student.status_code, 200, student.content)
        self.assertEqual(student['X-Document-Version'], str(self.version.pk))
