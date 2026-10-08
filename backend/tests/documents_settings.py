"""Isolated B2 test settings. Never use this to deploy the LMS."""
from config.settings.test import *
INSTALLED_APPS=INSTALLED_APPS+["tests.document_support.apps.DocumentSupportConfig"]
DOCUMENTS_COURSE_MODEL="document_test_support.Course"
DOCUMENTS_MANAGE_PERMISSION="tests.document_support.permissions.can_manage_course"
DOCUMENTS_READ_PERMISSION="tests.document_support.permissions.can_read_course"
MIGRATION_MODULES={"document_test_support":None}
ROOT_URLCONF="tests.documents_urls"
