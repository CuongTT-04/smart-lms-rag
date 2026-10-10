from django.urls import path
from .views import (
    CourseDocumentsView, DocumentStatusView, DocumentVersionsView,
    DocumentRetryView, DocumentDetailView, DocumentExtractionView,
    DocumentPublicationView, DocumentPolicyView, DocumentViewView, DocumentDownloadView,
)

app_name = "documents"
from .study_notes import StudyNotesView

course_urlpatterns = [path("", CourseDocumentsView.as_view(), name="course-documents")]

urlpatterns = [
    path("<uuid:document_id>/study-notes/", StudyNotesView.as_view(), name="study-notes"),
    path("<uuid:document_id>/publication/",DocumentPublicationView.as_view(),name="publication"),
    path("<uuid:document_id>/policy/",DocumentPolicyView.as_view(),name="policy"),
    path("<uuid:document_id>/view/",DocumentViewView.as_view(),name="view"),
    path("<uuid:document_id>/download/",DocumentDownloadView.as_view(),name="download"),
    path("<uuid:document_id>/status/", DocumentStatusView.as_view(), name="status"),
    path("<uuid:document_id>/versions/", DocumentVersionsView.as_view(), name="versions"),
    path("<uuid:document_id>/retry/", DocumentRetryView.as_view(), name="retry"),
    path("<uuid:document_id>/extraction/", DocumentExtractionView.as_view(), name="extraction"),
    path("<uuid:document_id>/", DocumentDetailView.as_view(), name="detail"),
]
