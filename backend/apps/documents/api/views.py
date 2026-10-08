"""JWT-only document API. Course models and authorization are supplied by A."""
import json
import uuid
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from .serializers import DocumentUploadRequest, DocumentRetryRequest
from ..access import course_model, require_access
from ..exceptions import DocumentError
from ..models import KnowledgeDocument
from ..services import upload_document, retry_ingestion, remove_document
from ..storage import private_path


def operation_payload(op):
    return {"document_id": str(op.document_id), "version_id": str(op.version_id),
            "job_id": str(op.job_id), "extraction_status": op.version.status,
            "rag_ready": False}


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
        if not manage and not document.is_published:
            require_access(request.user, document.course, manage=True)
        return document

    def version(self, request, document):
        version_id = request.data.get("version_id") if request.method == "POST" else request.query_params.get("version_id")
        queryset = document.versions.filter(removed_at__isnull=True)
        version = queryset.get(pk=version_id) if version_id else queryset.order_by("-version_number").first()
        if version is None:
            raise DocumentError("NOT_FOUND", "Version unavailable.", 404)
        return version


class CourseDocumentsView(DocumentAPIView):
    @extend_schema(tags=["Documents"], request={"multipart/form-data": DocumentUploadRequest}, responses={202: OpenApiTypes.OBJECT},
                   parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)])
    def post(self, request, course_id):
        course = course_model().objects.get(pk=course_id)
        op = upload_document(request.user, course, request.FILES.get("file"), request.data.get("title"), request.headers.get("Idempotency-Key"))
        return Response(operation_payload(op), status=202)

    @extend_schema(tags=["Documents"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, course_id):
        course = course_model().objects.get(pk=course_id)
        require_access(request.user, course)
        documents = KnowledgeDocument.objects.filter(course=course, removed_at__isnull=True).order_by("-created_at")
        try:
            require_access(request.user, course, manage=True)
        except DocumentError as exc:
            if exc.status != 404: raise
            documents = documents.filter(is_published=True)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(documents, request)
        rows = []
        for document in page:
            version = document.versions.filter(removed_at__isnull=True).order_by("-version_number").first()
            job = version.jobs.order_by("-created_at").first() if version else None
            rows.append({"document_id": str(document.pk), "title": document.title,
                "material_policy": document.material_policy, "is_published": document.is_published,
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
