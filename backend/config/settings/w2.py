"""Member B integration settings; A settings remain unchanged."""
from .local import *
import os
from pathlib import Path

ROOT_URLCONF = "config.urls"
DOCUMENTS_COURSE_MODEL = "courses.Course"
DOCUMENTS_MANAGE_PERMISSION = "apps.courses.permissions.can_manage_course"
DOCUMENTS_READ_PERMISSION = "apps.courses.permissions.can_view_course"
DOCUMENTS_STORAGE_ROOT = Path(os.getenv("DOCUMENTS_STORAGE_ROOT", str(BASE_DIR / ".private" / "documents")))
DOCUMENTS_MAX_BYTES = 20 * 1024 * 1024
DOCUMENTS_MAX_PAGES = 100
DOCUMENTS_TIMEOUT_SECONDS = 900
