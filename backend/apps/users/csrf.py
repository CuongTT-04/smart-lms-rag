"""CSRF and Origin/Referer verification for cookie-bearing auth endpoints."""
from urllib.parse import urlparse

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework.exceptions import APIException


class CsrfVerificationFailed(APIException):
    status_code = 403
    default_code = "CSRF_FAILED"
    default_detail = "CSRF verification failed."

    def __init__(self, detail=None):
        super().__init__(detail={"code": "CSRF_FAILED", "detail": detail or self.default_detail})


class _DRFCsrfCheck(CsrfViewMiddleware):
    def _reject(self, request, reason):
        return reason


def _normalize_origin(value):
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _trusted_origins(django_request):
    origins = set()
    for raw in (*getattr(settings, "CSRF_TRUSTED_ORIGINS", ()), *getattr(settings, "CORS_ALLOWED_ORIGINS", ())):
        norm = _normalize_origin(raw)
        if norm:
            origins.add(norm)
    frontend = _normalize_origin(getattr(settings, "FRONTEND_ORIGIN", ""))
    if frontend:
        origins.add(frontend)
    host = django_request.META.get("HTTP_HOST")
    if host:
        scheme = "https" if django_request.is_secure() else "http"
        same = _normalize_origin(f"{scheme}://{host}")
        if same:
            origins.add(same)
    return origins


def enforce_csrf_and_origin(request):
    """Enforce Origin/Referer allowlist and Django CSRF check when CSRF checks are enabled."""
    django_request = getattr(request, "_request", request)
    if getattr(django_request, "_dont_enforce_csrf_checks", False):
        return

    origin = django_request.META.get("HTTP_ORIGIN")
    referer = django_request.META.get("HTTP_REFERER")
    allowed = _trusted_origins(django_request)
    if origin is not None:
        normalized = _normalize_origin(origin)
        if not normalized or normalized not in allowed:
            raise CsrfVerificationFailed("Untrusted request origin.")
    elif referer is not None:
        normalized = _normalize_origin(referer)
        if not normalized or normalized not in allowed:
            raise CsrfVerificationFailed("Untrusted request referer.")

    reason = _DRFCsrfCheck(lambda req: None).process_view(django_request, None, (), {})
    if reason:
        raise CsrfVerificationFailed("CSRF token missing or incorrect.")
