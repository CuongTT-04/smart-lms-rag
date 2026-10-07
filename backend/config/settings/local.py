import os

from .base import *  # noqa: F403


DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

# The original local database was migrated with Django's default user model.
if (
    DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    and not os.getenv("DB_NAME")
):
    DATABASES["default"]["NAME"] = PROJECT_DIR / "db-w2.sqlite3"
