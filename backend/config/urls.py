from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health_check(_request):
    return JsonResponse({"status": "ok", "service": "smart-lms-rag"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health-check"),
    path("api/users/", include("apps.users.api.urls")),
    path("api/courses/", include("apps.courses.api.urls")),
    path("api/documents/", include("apps.documents.api.urls")),
    path("api/learning/", include("apps.learning.api.urls")),
    path("api/assessments/", include("apps.assessments.api.urls")),
    path("api/ai/", include("apps.ai.api.urls")),
    path("api/payments/", include("apps.payments.api.urls")),
    path("api/operations/", include("apps.operations.api.urls")),
]
