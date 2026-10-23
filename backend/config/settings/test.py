from .local import *  # noqa: F403


DEBUG = False

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Database integration tests use Django's isolated test_<NAME> PostgreSQL DB.
# Unit tests should use config.settings.unit and mock their I/O boundaries.

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
