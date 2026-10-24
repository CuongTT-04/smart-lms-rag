import os
from pathlib import Path
from dotenv import load_dotenv

# Docker supplies its own environment; only direct local runs read the root .env.
load_dotenv(Path(__file__).resolve().parents[3] / '.env', override=False)

from .base import *  # noqa: F403


DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
