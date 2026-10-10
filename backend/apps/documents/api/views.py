"""JWT-only document API. Course models and authorization are supplied by A."""
import json
import hashlib
import uuid
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from .serializers import DocumentUploadRequest, DocumentRetryRequest
from ..access import course_model, require_access, require_session_access
from ..exceptions import DocumentError
from ..models import KnowledgeDocument
from ..services import upload_document, retry_ingestion, remove_document, set_publication, set_material_policy
from ..storage import private_path


def operation_payload(op):
    return {"document_id": str(op.document_id), "version_id": str(op.version_id),
            "job_id": str(op.job_id), "extraction_status": op.version.status,
            "rag_ready": False}


def material_payload(document):
    return {"document_id":str(document.pk),"is_published":document.is_published,
            "published_version_id":str(document.published_version_id) if document.published_version_id else None,
            "material_policy":document.material_policy,"policy_revision":document.policy_revision}


def view_status(version):
    if version is None:return "NOT_STARTED"
    if version.watermark_status=="READY" and (not version.watermarked_view_key or not private_path(version.watermarked_view_key).is_file()):
        return "FAILED"
    return version.watermark_status


def is_manager(user,course):
    try:require_access(user,course,manage=True);return True
    except DocumentError as exc:
        if exc.status!=404:raise
        return False


class DocumentAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, DocumentError):
            return Response({"error": {"code": exc.code, "message": exc.message},
                             "request_id": str(uuid.uuid4())}, status=exc.status)
        if isinstance(exc, (ObjectDoesNotExist, ValidationError, ValueError)):
            return Response({"error": {"code": "NOT_FOUND", "message": "Resource unavailable."},
                             "request_id": str(uuid.uuid4())}, status=404)
        response = super().handle_exception(exc)
        code = "AUTH_REQUIRED" if response.status_code == 401 else "INVALID_REQUEST"
        response.data = {"error": {"code": code, "message": "Authentication required." if code == "AUTH_REQUIRED" else "Invalid request."},
                         "request_id": str(uuid.uuid4())}
        return response

    def document(self, request, document_id, manage=False):
        document = KnowledgeDocument.objects.select_related("course").get(pk=document_id, removed_at__isnull=True)
        require_access(request.user, document.course, manage=manage)
        if document.session_id:require_session_access(request.user,document.session,document.course,manage=manage)
        if not manage and not document.is_published:
            require_access(request.user, document.course, manage=True)
        return document

    def version(self, request, document):
        version_id = request.data.get("version_id") if request.method == "POST" else request.query_params.get("version_id")
        queryset = document.versions.filter(removed_at__isnull=True)
        if not is_manager(request.user,document.course):
            queryset=queryset.filter(pk=document.published_version_id)
        version = queryset.get(pk=version_id) if version_id else queryset.order_by("-version_number").first()
        if version is None:
            raise DocumentError("NOT_FOUND", "Version unavailable.", 404)
        return version


class CourseDocumentsView(DocumentAPIView):
    def session(self, request, course, session_id, manage=False):
        if not session_id:return None
        from apps.courses.models import ClassroomSession
        session=ClassroomSession.objects.select_related('classroom__course').get(pk=session_id, classroom__course_id=course.pk)
        require_session_access(request.user, session, course, manage=manage)
        return session

    @extend_schema(tags=["Documents"], summary="Upload course material", description="The active course owner uploads a PDF. Returns a durable extraction job after storing the source privately; document processing runs separately in the worker.",
                   request={"multipart/form-data": DocumentUploadRequest}, responses={202: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
                   parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)])
    def post(self, request, course_id):
        course = course_model().objects.get(pk=course_id)
        session = self.session(request, course, request.data.get("session_id"), manage=True)
        op = upload_document(request.user, course, request.FILES.get("file"), request.data.get("title"), request.headers.get("Idempotency-Key"), session=session)
        return Response(operation_payload(op), status=202)

    @extend_schema(tags=["Documents"], summary="List course materials", description="List material metadata using current course permissions. Students only see published materials; no private storage paths are returned.",
                   responses={200: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT})
    def get(self, request, course_id):
        course = course_model().objects.get(pk=course_id)
        require_access(request.user, course)
        documents = KnowledgeDocument.objects.filter(course=course, removed_at__isnull=True).order_by("-created_at")
        session=self.session(request, course, request.query_params.get('session_id'))
        if session:documents=documents.filter(session=session)
        elif request.query_params.get('scope')=='course':documents=documents.filter(session__isnull=True)
        try:
            require_access(request.user, course, manage=True)
        except DocumentError as exc:
            if exc.status != 404: raise
            from apps.courses.models import Enrollment
            rooms=Enrollment.objects.filter(student__user=request.user,status__in=['ACTIVE','COMPLETED'],classroom__course_id=course.pk).values('classroom_id')
            documents = documents.filter(is_published=True,published_version__isnull=False).filter(Q(session__isnull=True)|Q(session__classroom_id__in=rooms))
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(documents, request)
        rows = []
        for document in page:
            version = (document.versions.filter(removed_at__isnull=True).order_by("-version_number").first()
                       if is_manager(request.user,course) else document.published_version)
            job = version.jobs.order_by("-created_at").first() if version else None
            rows.append({"document_id": str(document.pk), "title": document.title,"session_id":str(document.session_id) if document.session_id else None,
                **material_payload(document),
                "watermark_status":view_status(version),
                "version_id": str(version.pk) if version else None,
                "file_name": version.file_name if version else None,
                "page_count": version.page_count if version else None,
                "extraction_status": version.status if version else "NOT_STARTED",
                "error_code": job.error_code if job else "", "rag_ready": False})
        return paginator.get_paginated_response(rows)



class DocumentStatusView(DocumentAPIView):
    @extend_schema(tags=["Documents"], responses={200: OpenApiTypes.OBJECT},
                   parameters=[OpenApiParameter("version_id", OpenApiTypes.UUID)])
    def get(self, request, document_id):
        document = self.document(request, document_id)
        version = self.version(request, document)
        job = version.jobs.order_by("-created_at").first()
        return Response({"document_id": str(document.pk), "version_id": str(version.pk),
            "extraction_status": version.status, "pipeline_status": version.status,
            "page_count": version.page_count, "file_name": version.file_name,
            "job_status": job.status if job else None, "error_code": job.error_code if job else "",
            "extracted_at": version.extracted_at, "indexed_at": version.indexed_at,
            "watermark_status":view_status(version),
            **material_payload(document),
            "rag_ready": False})


class DocumentVersionsView(DocumentAPIView):
    @extend_schema(tags=["Documents"], request={"multipart/form-data": DocumentUploadRequest}, responses={202: OpenApiTypes.OBJECT},
                   parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)])
    def post(self, request, document_id):
        document = self.document(request, document_id, manage=True)
        op = upload_document(request.user, document.course, request.FILES.get("file"), document.title,
                             request.headers.get("Idempotency-Key"), document=document)
        return Response(operation_payload(op), status=202)


class DocumentRetryView(DocumentAPIView):
    @extend_schema(tags=["Documents"], request=DocumentRetryRequest, responses={202: OpenApiTypes.OBJECT},
                   parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)])
    def post(self, request, document_id):
        document = self.document(request, document_id, manage=True)
        if not request.data.get("version_id"):
            raise DocumentError("VERSION_REQUIRED", "Provide version_id.", 400)
        version = self.version(request, document)
        op = retry_ingestion(request.user, document, version, request.headers.get("Idempotency-Key"))
        return Response(operation_payload(op), status=202)


class DocumentDetailView(DocumentAPIView):
    @extend_schema(tags=["Documents"], summary="Rename material", request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def patch(self, request, document_id):
        document = self.document(request, document_id, manage=True)
        title = request.data.get("title")
        if set(request.data) != {"title"} or not isinstance(title, str) or not title.strip() or len(title.strip()) > 255:
            raise DocumentError("INVALID_TITLE", "A title of 1 to 255 characters is required.", 400)
        document.title = title.strip()
        document.save(update_fields=["title", "updated_at"])
        return Response({"document_id": str(document.pk), "title": document.title})

    @extend_schema(tags=["Documents"], responses={204: None})
    def delete(self, request, document_id):
        document = self.document(request, document_id, manage=True)
        remove_document(request.user, document)
        return Response(status=204)


class DocumentExtractionView(DocumentAPIView):
    @extend_schema(tags=["Documents"], responses={200: OpenApiTypes.OBJECT},
                   parameters=[OpenApiParameter("version_id", OpenApiTypes.UUID)])
    def get(self, request, document_id):
        document = self.document(request, document_id, manage=True)
        version = self.version(request, document)
        if version.status not in {"EXTRACTED", "READY"} or not version.extracted_storage_key:
            raise DocumentError("EXTRACTION_NOT_READY", "Extraction is not available.", 409)
        try:
            payload = json.loads(private_path(version.extracted_storage_key).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DocumentError("EXTRACTION_UNAVAILABLE", "Extraction is unavailable.", 503) from exc
        for key, value in (("course_id", document.course_id), ("document_id", document.pk), ("version_id", version.pk)):
            if payload.get(key) != str(value):
                raise DocumentError("EXTRACTION_UNAVAILABLE", "Extraction scope mismatch.", 503)
        self.document(request, document_id, manage=True)
        version.refresh_from_db()
        if version.removed_at:
            raise DocumentError("NOT_FOUND", "Resource unavailable.", 404)
        return Response(payload)


class DocumentPublicationView(DocumentAPIView):
    @extend_schema(tags=["Documents"],request=OpenApiTypes.OBJECT,responses={200:OpenApiTypes.OBJECT})
    def patch(self,request,document_id):
        document=self.document(request,document_id,manage=True)
        if set(request.data)-{"is_published","version_id"}:raise DocumentError("INVALID_PUBLICATION","Unknown publication fields.",400)
        document=set_publication(request.user,document,request.data.get("is_published"),request.data.get("version_id"))
        return Response(material_payload(document))


class DocumentPolicyView(DocumentAPIView):
    @extend_schema(tags=["Documents"],request=OpenApiTypes.OBJECT,responses={200:OpenApiTypes.OBJECT})
    def patch(self,request,document_id):
        document=self.document(request,document_id,manage=True)
        if set(request.data)-{"material_policy","policy_revision"}:raise DocumentError("INVALID_POLICY","Unknown policy fields.",400)
        document=set_material_policy(request.user,document,request.data.get("material_policy"),request.data.get("policy_revision"))
        return Response(material_payload(document))


class DocumentViewView(DocumentAPIView):
    download=False

    @extend_schema(tags=["Documents"],responses={(200,"application/pdf"):OpenApiTypes.BINARY})
    def get(self,request,document_id):
        # Read under the same document lock used by policy/publication/removal.
        with transaction.atomic():
            # Load the nullable version separately: PostgreSQL cannot lock a LEFT JOIN's nullable side.
            document=KnowledgeDocument.objects.select_for_update().select_related("course").get(pk=document_id,removed_at__isnull=True)
            request.user.refresh_from_db();require_access(request.user,document.course)
            if document.session_id:require_session_access(request.user,document.session,document.course)
            manager=is_manager(request.user,document.course)
            if not manager and not document.is_published:raise DocumentError("NOT_FOUND","Resource unavailable.",404)
            version=document.published_version
            if manager and (self.download or request.query_params.get("version_id")):
                version=self.version(request,document)
            if version is None and manager:version=self.version(request,document)
            if not version or version.removed_at:raise DocumentError("VIEW_NOT_READY","No view version available.",409)
            if self.download and not manager and document.material_policy!="PUBLIC_DOWNLOAD":raise DocumentError("DOWNLOAD_DISABLED","Clean download is disabled.",403)
            protected=not self.download and document.material_policy=="PROTECTED"
            if not (self.download and manager) and (version.status not in {"EXTRACTED","READY"} or (protected and version.watermark_status!="READY")):
                raise DocumentError("VIEW_NOT_READY","View is not ready.",409)
            key=version.watermarked_view_key if protected else version.original_storage_key
            checksum=version.watermarked_sha256 if protected else version.checksum_sha256
            if not key:raise DocumentError("VIEW_UNAVAILABLE","View unavailable.",503)
            try:content=private_path(key).read_bytes()
            except OSError as exc:raise DocumentError("VIEW_UNAVAILABLE","View unavailable.",503) from exc
            if hashlib.sha256(content).hexdigest()!=checksum:raise DocumentError("VIEW_UNAVAILABLE","View checksum mismatch.",503)
            request.user.refresh_from_db();require_access(request.user,document.course,manage=not document.is_published)
            if document.session_id:require_session_access(request.user,document.session,document.course,manage=not document.is_published)
            response=HttpResponse(content,content_type="application/pdf")
            from django.utils.http import content_disposition_header
            response["Content-Disposition"]=content_disposition_header(self.download,version.file_name)
            response["Cache-Control"]="private, no-store"
            response["X-Content-Type-Options"]="nosniff"
            response["X-Document-Version"]=str(version.pk)
            response["X-Policy-Revision"]=str(document.policy_revision)
            return response


class DocumentDownloadView(DocumentViewView):
    download=True
