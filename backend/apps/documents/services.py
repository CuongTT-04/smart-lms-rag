import hashlib
import json
import uuid
from django.db import transaction,IntegrityError
from django.db.models import Max
from django.utils import timezone
from .models import KnowledgeDocument,DocumentVersion,IngestionJob,DocumentOperation
from .storage import stage_upload,private_path
from .access import require_access
from .exceptions import DocumentError

def _digest(payload):return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def _key(key):
    if not isinstance(key,str) or not key.strip() or len(key)>128:
        raise DocumentError("IDEMPOTENCY_KEY_REQUIRED","Provide Idempotency-Key (1-128 characters).",400)
    return key

def _existing(actor,course,action,key,digest):
    op=DocumentOperation.objects.filter(actor=actor,course=course,action=action,client_key=key).select_related("document","version","job").first()
    if op:
        if op.payload_digest!=digest:raise DocumentError("IDEMPOTENCY_CONFLICT","Key already used for another payload.",409)
        if not op.document or op.document.removed_at or not op.version or op.version.removed_at:
            raise DocumentError("NOT_FOUND","Resource unavailable.",404)
    return op

def upload_document(user,course,upload,title,key,document=None):
    require_access(user,course,manage=True);key=_key(key)
    title=str(title or getattr(upload,"name","Document"))
    if len(title)>255:raise DocumentError("INVALID_TITLE","Title exceeds 255 characters.",400)
    staged,size,checksum,pages=stage_upload(upload)
    final=None;committed=False
    action="REPLACE" if document else "UPLOAD"
    digest=_digest({"checksum":checksum,"title":title,"file_name":getattr(upload,"name","document.pdf"),"document_id":str(document.pk) if document else None})
    try:
        existing=_existing(user,course,action,key,digest)
        if existing:return existing
        try:
            with transaction.atomic():
                course.refresh_from_db();user.refresh_from_db();require_access(user,course,manage=True)
                op=DocumentOperation.objects.create(actor=user,course=course,action=action,client_key=key,payload_digest=digest)
                if document:
                    document=KnowledgeDocument.objects.select_for_update().get(pk=document.pk,course=course,removed_at__isnull=True)
                else:document=KnowledgeDocument.objects.create(course=course,uploaded_by=user,title=title)
                number=(document.versions.aggregate(last=Max("version_number"))["last"] or 0)+1
                version_id=uuid.uuid4();storage_key=f"originals/{document.pk}/{version_id}.pdf"
                final=private_path(storage_key);final.parent.mkdir(parents=True,exist_ok=True);staged.replace(final)
                version=DocumentVersion.objects.create(id=version_id,document=document,version_number=number,
                    file_name=str(getattr(upload,"name","document.pdf"))[:255],file_size_bytes=size,
                    checksum_sha256=checksum,page_count=pages,original_storage_key=storage_key)
                job=IngestionJob.objects.create(document_version=version,idempotency_key=uuid.uuid4().hex,payload_digest=checksum)
                op.document=document;op.version=version;op.job=job;op.save(update_fields=["document","version","job"])
            committed=True;return op
        except IntegrityError:
            existing=_existing(user,course,action,key,digest)
            if existing:return existing
            raise
    finally:
        staged.unlink(missing_ok=True)
        if final is not None and not committed:final.unlink(missing_ok=True)

def retry_ingestion(user,document,version,key):
    require_access(user,document.course,manage=True);key=_key(key)
    digest=_digest({"document_id":str(document.pk),"version_id":str(version.pk)})
    existing=_existing(user,document.course,"RETRY",key,digest)
    if existing:return existing
    try:
        with transaction.atomic():
            locked=KnowledgeDocument.objects.select_for_update().get(pk=document.pk,removed_at__isnull=True)
            require_access(user,locked.course,manage=True)
            version=DocumentVersion.objects.select_for_update().get(pk=version.pk,document=locked,removed_at__isnull=True)
            if version.status!="FAILED":raise DocumentError("RETRY_NOT_ALLOWED","Only failed extraction can be retried.",409)
            if version.jobs.filter(status__in=["QUEUED","RUNNING"]).exists():
                raise DocumentError("RETRY_NOT_ALLOWED","An extraction job is already active.",409)
            op=DocumentOperation.objects.create(actor=user,course=locked.course,action="RETRY",client_key=key,payload_digest=digest,document=locked,version=version)
            job=IngestionJob.objects.create(document_version=version,idempotency_key=uuid.uuid4().hex,payload_digest=version.checksum_sha256)
            version.status="QUEUED";version.save(update_fields=["status"])
            op.job=job;op.save(update_fields=["job"]);return op
    except IntegrityError:
        existing=_existing(user,document.course,"RETRY",key,digest)
        if existing:return existing
        raise

def remove_document(user,document):
    with transaction.atomic():
        document=KnowledgeDocument.objects.select_for_update().get(pk=document.pk)
        require_access(user,document.course,manage=True)
        now=timezone.now();document.removed_at=now;document.active_version=None;document.save(update_fields=["removed_at","active_version","updated_at"])
        document.versions.update(removed_at=now,status="REMOVED")
        IngestionJob.objects.filter(document_version__document=document,status__in=["QUEUED","RUNNING"]).update(status="CANCELLED",worker_token=None,finished_at=now,error_code="SOURCE_REMOVED")
