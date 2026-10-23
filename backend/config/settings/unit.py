"""Mock-only unit tests: accidental SQL fails instead of accessing any database."""
from .test import *  # noqa: F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.dummy'}}
