from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common.schema import HealthSerializer


@extend_schema(
    operation_id="health_check", tags=["System"],
    summary="Check backend health", responses={200: HealthSerializer}, auth=[],
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_check(_request):
    return Response({"status": "ok", "service": "smart-lms-rag"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="api-schema",
            template_name_js="drf_spectacular/swagger_ui_jwt.js",
        ),
        name="swagger-ui",
    ),
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

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
