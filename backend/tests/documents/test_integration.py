"""Integration uses A User, Course, JWT login and membership APIs unchanged."""
import io
import tempfile
from pathlib import Path
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from reportlab.pdfgen.canvas import Canvas
from apps.documents.models import KnowledgeDocument, DocumentVersion
from apps.documents.worker import claim_job, process_job
from apps.documents.processors.parser import ExtractionResult, ExtractedPage
from apps.courses.models import CourseMember

class AIntegrationTests(TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        config=override_settings(DOCUMENTS_STORAGE_ROOT=Path(self.folder.name));config.enable();self.addCleanup(config.disable)
        User=get_user_model()
        self.teacher=User.objects.create_user("teacher",password="Teacher123!",role="TEACHER")
        self.student=User.objects.create_user("student",password="Student123!")
        self.other=User.objects.create_user("other",password="Teacher123!",role="TEACHER")
        self.admin=User.objects.create_superuser("admin",password="Admin123!")
        self.client=Client(enforce_csrf_checks=True)
        self.login("teacher","Teacher123!")
        response=self.client.post("/api/courses/",{"title":"Integrated course"},content_type="application/json")
        self.assertEqual(response.status_code,201,response.content);self.course_id=response.json()["id"]
        response=self.client.patch(f"/api/courses/{self.course_id}/",{"status":"PUBLISHED"},content_type="application/json")
        self.assertEqual(response.status_code,200,response.content)
        self.client.post(f"/api/courses/{self.course_id}/classrooms/", {"name":"Integration class"}, content_type="application/json")
        response=self.client.get(f"/api/courses/{self.course_id}/classrooms/")
        self.assertEqual(response.status_code,200,response.content)
        self.classroom=response.json()["results"][0]
        self.login("student","Student123!")
        response=self.client.post("/api/courses/join/",{"class_code":self.classroom["class_code"]},content_type="application/json")
        self.assertEqual(response.status_code,201,response.content)
        self.enrollment_id=response.json()["enrollment"]["id"]
        self.member_id=str(CourseMember.objects.get(course_id=self.course_id,user=self.student).pk)
        self.login("teacher","Teacher123!")
        self.url=f"/api/courses/{self.course_id}/documents/"
    def login(self,username,password):
        self.client.defaults.pop("HTTP_AUTHORIZATION",None)
        response=self.client.post("/api/users/login/",{"username":username,"password":password},content_type="application/json")
        self.assertEqual(response.status_code,200,response.content)
        self.client.defaults["HTTP_AUTHORIZATION"]="Bearer "+response.json()["access"]
        return response
    def upload(self):
        buf=io.BytesIO();c=Canvas(buf);c.drawString(30,700,"PAGE ONE");c.showPage();c.save()
        return self.client.post(self.url,{"title":"Document","file":SimpleUploadedFile("sample.pdf",buf.getvalue())},HTTP_IDEMPOTENCY_KEY="upload")
    def test_actual_A_login_membership_upload_and_revocation(self):
        response=self.upload();self.assertEqual(response.status_code,202,response.content)
        document_id=response.json()["document_id"]
        self.login("student","Student123!")
        self.assertEqual(self.client.post(self.url,{}).status_code,404)
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/status/").status_code,404)
        KnowledgeDocument.objects.filter(pk=document_id).update(is_published=True,published_version_id=DocumentVersion.objects.get(document_id=document_id).pk)
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/status/").status_code,200)
        self.login("teacher","Teacher123!")
        response=self.client.delete(f"/api/courses/{self.course_id}/members/{self.member_id}/")
        self.assertEqual(response.status_code,204,response.content)
        self.login("student","Student123!")
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/status/").status_code,404)
    def test_A_admin_and_other_teacher_cannot_manage_documents(self):
        for username,password in [("other","Teacher123!"),("admin","Admin123!")]:
            self.login(username,password)
            self.assertEqual(self.upload().status_code,404)
    def test_A_refresh_cookie_does_not_authenticate_document_API(self):
        self.client.defaults.pop("HTTP_AUTHORIZATION")
        self.assertEqual(self.upload().status_code,401)
        refreshed=self.client.post("/api/users/token/refresh/")
        self.assertEqual(refreshed.status_code,200,refreshed.content)
        self.client.defaults["HTTP_AUTHORIZATION"]="Bearer "+refreshed.json()["access"]
        self.assertEqual(self.upload().status_code,202)
    def test_extraction_uses_real_course_UUID_and_current_owner(self):
        response=self.upload();self.assertEqual(response.status_code,202,response.content)
        job=claim_job()
        def result(source,version):
            return ExtractionResult(1,(ExtractedPage(1,"PAGE ONE","OK"),),"test",version.checksum_sha256)
        process_job(job,runner=result)
        version=DocumentVersion.objects.get()
        response=self.client.get(f"/api/documents/{version.document_id}/extraction/")
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()["course_id"],self.course_id)
        self.assertFalse(response.json()["rag_ready"])

    def test_list_exposes_safe_version_metadata_for_UI(self):
        uploaded=self.upload();self.assertEqual(uploaded.status_code,202,uploaded.content)
        response=self.client.get(self.url)
        row=response.json()["results"][0]
        self.assertEqual(row.get("version_id"),uploaded.json()["version_id"])
        self.assertEqual(row.get("page_count"),1)
        self.assertEqual(row.get("extraction_status"),"QUEUED")
        self.assertNotIn("original_storage_key",row)

    def test_archived_course_blocks_student_but_preserves_owner_management(self):
        uploaded=self.upload();document_id=uploaded.json()["document_id"]
        KnowledgeDocument.objects.filter(pk=document_id).update(is_published=True,published_version_id=DocumentVersion.objects.get(document_id=document_id).pk)
        self.assertEqual(self.client.patch(f"/api/courses/{self.course_id}/",{"status":"ARCHIVED"},content_type="application/json").status_code,200)
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/status/").status_code,200)
        self.login("student","Student123!")
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/status/").status_code,404)

    def test_published_metadata_never_grants_student_extraction_or_original(self):
        uploaded=self.upload();document_id=uploaded.json()["document_id"]
        KnowledgeDocument.objects.filter(pk=document_id).update(is_published=True,published_version_id=DocumentVersion.objects.get(document_id=document_id).pk)
        self.login("student","Student123!")
        self.assertEqual(self.client.get(self.url).status_code,200)
        for suffix in ("extraction/",):
            self.assertEqual(self.client.get(f"/api/documents/{document_id}/{suffix}").status_code,404)

    def test_replace_keeps_protected_policy_and_separate_versions(self):
        uploaded=self.upload();document_id=uploaded.json()["document_id"]
        file=self.upload_file()
        response=self.client.post(f"/api/documents/{document_id}/versions/",{"file":file},HTTP_IDEMPOTENCY_KEY="replace")
        self.assertEqual(response.status_code,202,response.content)
        document=KnowledgeDocument.objects.get(pk=document_id)
        self.assertEqual(document.material_policy,"PROTECTED")
        self.assertEqual(document.versions.count(),2)
        self.assertIsNone(document.active_version_id)
        self.assertNotEqual(response.json()["version_id"],uploaded.json()["version_id"])

    def upload_file(self):
        stream=io.BytesIO();canvas=Canvas(stream);canvas.drawString(30,700,"REPLACEMENT");canvas.showPage();canvas.save()
        return SimpleUploadedFile("replacement.pdf",stream.getvalue())

    def test_removal_blocks_all_metadata_and_extraction_even_for_owner(self):
        uploaded=self.upload();document_id=uploaded.json()["document_id"]
        self.assertEqual(self.client.delete(f"/api/documents/{document_id}/").status_code,204)
        self.assertEqual(self.client.get(self.url).json()["results"],[])
        for suffix in ("status/","extraction/"):
            self.assertEqual(self.client.get(f"/api/documents/{document_id}/{suffix}").status_code,404)

    def test_classroom_withdrawal_keeps_material_access_until_last_enrollment_removed(self):
        document_id=self.upload().json()["document_id"]
        KnowledgeDocument.objects.filter(pk=document_id).update(is_published=True,published_version_id=DocumentVersion.objects.get(document_id=document_id).pk)
        response=self.client.post(f"/api/courses/{self.course_id}/classrooms/",{"name":"Second classroom"},content_type="application/json")
        self.assertEqual(response.status_code,201,response.content);second=response.json()
        self.login("student","Student123!")
        response=self.client.post("/api/courses/join/",{"class_code":second["class_code"]},content_type="application/json")
        self.assertEqual(response.status_code,201,response.content);second_enrollment=response.json()["enrollment"]["id"]
        self.login("teacher","Teacher123!")
        response=self.client.delete(f"/api/courses/{self.course_id}/classrooms/{self.classroom['id']}/enrollments/{self.enrollment_id}/")
        self.assertEqual(response.status_code,204,response.content)
        self.login("student","Student123!")
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/status/").status_code,200)
        self.login("teacher","Teacher123!")
        response=self.client.delete(f"/api/courses/{self.course_id}/classrooms/{second['id']}/enrollments/{second_enrollment}/")
        self.assertEqual(response.status_code,204,response.content)
        self.login("student","Student123!")
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/status/").status_code,404)

    def test_pending_request_cannot_read_materials_until_teacher_approves(self):
        document_id=self.upload().json()["document_id"]
        KnowledgeDocument.objects.filter(pk=document_id).update(is_published=True,published_version_id=DocumentVersion.objects.get(document_id=document_id).pk)
        response=self.client.patch(f"/api/courses/{self.course_id}/classrooms/{self.classroom['id']}/",{"require_approval":True},content_type="application/json")
        self.assertEqual(response.status_code,200,response.content)
        get_user_model().objects.create_user("waiting",password="Student123!")
        self.login("waiting","Student123!")
        response=self.client.post("/api/courses/join/",{"class_code":self.classroom["class_code"]},content_type="application/json")
        self.assertEqual(response.status_code,201,response.content)
        self.assertEqual(response.json()["status"],"PENDING");request_id=response.json()["join_request"]["id"]
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/status/").status_code,404)
        self.login("teacher","Teacher123!")
        response=self.client.post(f"/api/courses/{self.course_id}/join-requests/{request_id}/review/",{"decision":"approve"},content_type="application/json")
        self.assertEqual(response.status_code,200,response.content)
        self.login("waiting","Student123!")
        self.assertEqual(self.client.get(f"/api/documents/{document_id}/status/").status_code,200)

    def test_direct_member_grant_is_no_longer_a_supported_join_flow(self):
        response=self.client.post(f"/api/courses/{self.course_id}/members/",{"user_id":str(self.student.pk)},content_type="application/json")
        self.assertEqual(response.status_code,405)
