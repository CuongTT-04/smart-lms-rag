from django.urls import path
from .views import (
    CourseDocumentsView, DocumentStatusView, DocumentVersionsView,
    DocumentRetryView, DocumentDetailView, DocumentExtractionView,
)

app_name = "documents"

course_urlpatterns = [path("", CourseDocumentsView.as_view(), name="course-documents")]

urlpatterns = [
    path("<uuid:document_id>/status/", DocumentStatusView.as_view(), name="status"),
    path("<uuid:document_id>/versions/", DocumentVersionsView.as_view(), name="versions"),
    path("<uuid:document_id>/retry/", DocumentRetryView.as_view(), name="retry"),
    path("<uuid:document_id>/extraction/", DocumentExtractionView.as_view(), name="extraction"),
    path("<uuid:document_id>/", DocumentDetailView.as_view(), name="detail"),
]
