import os

from .base import *  # noqa: F403


# Local Docker development; production requires its own HTTPS/static setup.
DEBUG = env_bool("DJANGO_DEBUG", True)
PASSWORD_RESET_PREVIEW = env_bool("PASSWORD_RESET_PREVIEW", True)
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
