import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
COURSE_MODEL=getattr(settings,"DOCUMENTS_COURSE_MODEL","courses.Course")

class DocumentBase(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: abstract=True

class KnowledgeDocument(DocumentBase):
    session=models.ForeignKey("courses.ClassroomSession",null=True,blank=True,on_delete=models.PROTECT,related_name="materials")
    course=models.ForeignKey(COURSE_MODEL,on_delete=models.PROTECT,related_name="learning_documents")
    uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="uploaded_documents")
    title=models.CharField(max_length=255)
    material_policy=models.CharField(max_length=20,choices=[("PROTECTED","Protected"),("PUBLIC_DOWNLOAD","Public download")],default="PROTECTED")
    policy_revision=models.PositiveIntegerField(default=1)
    is_published=models.BooleanField(default=False)
    active_version=models.ForeignKey("DocumentVersion",null=True,blank=True,on_delete=models.PROTECT,related_name="active_for_documents")
    published_version=models.ForeignKey("DocumentVersion",null=True,blank=True,on_delete=models.PROTECT,related_name="published_for_documents")
    removed_at=models.DateTimeField(null=True,blank=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        indexes=[models.Index(fields=["course","removed_at","is_published"],name="doc_course_scope_idx")]

class DocumentVersion(DocumentBase):
    document=models.ForeignKey(KnowledgeDocument,on_delete=models.PROTECT,related_name="versions")
    version_number=models.PositiveIntegerField()
    file_name=models.CharField(max_length=255)
    file_type=models.CharField(max_length=10,default="PDF")
    original_storage_key=models.CharField(max_length=255)
    file_size_bytes=models.PositiveBigIntegerField()
    checksum_sha256=models.CharField(max_length=64)
    page_count=models.PositiveIntegerField()
    extracted_storage_key=models.CharField(max_length=255,blank=True,default="")
    watermarked_view_key=models.CharField(max_length=255,blank=True,default="")
    watermarked_sha256=models.CharField(max_length=64,blank=True,default="")
    watermark_status=models.CharField(max_length=20,default="NOT_STARTED")
    status=models.CharField(max_length=20,choices=[(s,s) for s in ("QUEUED","PROCESSING","EXTRACTED","READY","FAILED","REMOVED")],default="QUEUED")
    ocr_used=models.BooleanField(default=False)
    extracted_at=models.DateTimeField(null=True,blank=True)
    indexed_at=models.DateTimeField(null=True,blank=True)
    removed_at=models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["document","version_number"],name="doc_version_number_unique"),
          models.CheckConstraint(condition=Q(version_number__gte=1),name="doc_version_positive"),
          models.CheckConstraint(condition=Q(file_size_bytes__gt=0),name="doc_size_positive")]

class IngestionJob(DocumentBase):
    document_version=models.ForeignKey(DocumentVersion,on_delete=models.PROTECT,related_name="jobs")
    job_type=models.CharField(max_length=20,default="EXTRACT")
    idempotency_key=models.CharField(max_length=64,unique=True)
    payload_digest=models.CharField(max_length=64)
    status=models.CharField(max_length=20,choices=[(s,s) for s in ("QUEUED","RUNNING","SUCCEEDED","FAILED","CANCELLED")],default="QUEUED")
    attempt_count=models.PositiveIntegerField(default=0)
    worker_token=models.UUIDField(null=True,blank=True)
    lease_expires_at=models.DateTimeField(null=True,blank=True)
    started_at=models.DateTimeField(null=True,blank=True)
    finished_at=models.DateTimeField(null=True,blank=True)
    error_code=models.CharField(max_length=64,blank=True,default="")
    class Meta:
        indexes=[models.Index(fields=["status","created_at"],name="doc_job_queue_idx")]

class DocumentOperation(DocumentBase):
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    course=models.ForeignKey(COURSE_MODEL,on_delete=models.PROTECT)
    action=models.CharField(max_length=20)
    client_key=models.CharField(max_length=128)
    payload_digest=models.CharField(max_length=64)
    document=models.ForeignKey(KnowledgeDocument,null=True,on_delete=models.PROTECT)
    version=models.ForeignKey(DocumentVersion,null=True,on_delete=models.PROTECT)
    job=models.ForeignKey(IngestionJob,null=True,on_delete=models.PROTECT)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["actor","course","action","client_key"],name="doc_request_idempotent")]
