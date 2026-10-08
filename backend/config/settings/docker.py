import os
from pathlib import Path

from .base import *  # noqa: F403


# Local Docker development; production requires its own HTTPS/static setup.
DEBUG = env_bool("DJANGO_DEBUG", True)
PASSWORD_RESET_PREVIEW = env_bool("PASSWORD_RESET_PREVIEW", True)
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DOCUMENTS_STORAGE_ROOT = Path(os.getenv("DOCUMENTS_STORAGE_ROOT", str(BASE_DIR / ".private" / "documents")))
DOCUMENTS_MAX_BYTES = 20 * 1024 * 1024
DOCUMENTS_MAX_PAGES = 100
DOCUMENTS_TIMEOUT_SECONDS = 900
