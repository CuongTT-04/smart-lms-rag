from copy import deepcopy
import json
import os
import subprocess
import sys
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection, IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings

from apps.courses.models import CourseMember
from apps.documents.models import DocumentStudyNotes, DocumentVersion, KnowledgeDocument
from apps.notifications.models import Notification
from tests.documents import test_material_access as material


class StudyAnnotationTests(TestCase):
    setUp = material.MaterialAccessTests.setUp
    login = material.MaterialAccessTests.login
    upload = material.MaterialAccessTests.upload
    upload_file = material.MaterialAccessTests.upload_file
    prepare = material.MaterialAccessTests.prepare
    publish = material.MaterialAccessTests.publish

    def prepare_notes(self):
        self.prepare()
        self.assertEqual(self.publish().status_code, 200)
        self.notes_url = self.base + f'study-notes/?version_id={self.version.pk}'
        self.login('student', 'Student123!')
        self.payload = {'items': [
            {'id': 'pen', 'page': 1, 'kind': 'pen', 'points': [[0.1, 0.2], [0.3, 0.4]]},
            {'id': 'highlight', 'page': 1, 'kind': 'highlight', 'points': [[0.1, 0.5], [0.8, 0.5]]},
            {'id': 'text', 'page': 1, 'kind': 'text', 'x': 0.2, 'y': 0.3, 'text': 'Annotation'},
        ], 'notes': '  My note\nSecond line  '}
        self.payload['scope'] = self.client.get(self.notes_url).json()['scope']

    def save_notes(self, payload=None):
        response = self.client.put(self.notes_url, payload or self.payload, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def test_annotations_are_private_durable_and_independent_of_cache(self):
        self.prepare_notes()
        payload = deepcopy(self.payload)
        payload['feedback'] = {'vote': 'like', 'report': {'reason': 'Incorrect page', 'opinion': 'Please review'}}
        self.save_notes(payload)
        note = DocumentStudyNotes.objects.get(user=self.student, version=self.version)
        self.assertEqual(note.items, payload['items'])
        self.assertEqual(note.notes, payload['notes'])
        self.assertEqual(note.feedback, payload['feedback'])
        cache.clear()
        self.assertEqual(self.client.get(self.notes_url).json(), payload)
        self.assertEqual(self.client.get(self.notes_url)['Cache-Control'], 'private, no-store')
        self.login('teacher', 'Teacher123!')
        self.assertEqual(self.client.get(self.notes_url).json()['items'], [])
        self.assertEqual(self.client.put(self.notes_url, payload, content_type='application/json').status_code, 409)
        self.login('other', 'Teacher123!')
        self.assertEqual(self.client.get(self.notes_url).status_code, 404)

    def test_get_does_not_create_an_empty_database_row(self):
        self.prepare_notes()
        self.assertEqual(DocumentStudyNotes.objects.count(), 0)

    def test_full_replacement_and_clear_keep_a_single_row(self):
        self.prepare_notes()
        self.save_notes()
        payload = {'scope': self.payload['scope'], 'items': [], 'notes': ''}
        self.save_notes(payload)
        self.assertEqual(self.client.get(self.notes_url).json(), payload)
        self.assertEqual(DocumentStudyNotes.objects.filter(user=self.student, version=self.version).count(), 1)

    def test_database_prevents_duplicate_user_version_rows(self):
        self.prepare_notes()
        self.save_notes()
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentStudyNotes.objects.create(user=self.student, version=self.version)

    def test_wrong_or_legacy_scope_does_not_overwrite_notes(self):
        self.prepare_notes()
        self.save_notes()
        for scope in ('old-process:user:version', 'study-v1:forged', None):
            payload = {**self.payload, 'scope': scope, 'notes': 'Wrong write'}
            self.assertEqual(self.client.put(self.notes_url, payload, content_type='application/json').status_code, 409)
        with override_settings(SECRET_KEY='rotated-test-key'):
            self.assertEqual(self.client.put(self.notes_url, self.payload, content_type='application/json').status_code, 409)
        self.assertEqual(self.client.get(self.notes_url).json(), self.payload)

    def test_new_version_is_empty_and_old_notes_are_retained_but_not_exposed(self):
        self.prepare_notes()
        self.save_notes()
        newer = DocumentVersion.objects.create(document=self.version.document, version_number=2,
            file_name='new.pdf', original_storage_key='new.pdf', file_size_bytes=1, checksum_sha256='b'*64,
            page_count=1, status='EXTRACTED')
        KnowledgeDocument.objects.filter(pk=self.document_id).update(published_version=newer, active_version=newer)
        self.assertEqual(self.client.get(self.notes_url).status_code, 404)
        new_url = self.base + f'study-notes/?version_id={newer.pk}'
        saved = self.client.get(new_url).json()
        self.assertEqual(saved['items'], [])
        self.assertEqual(saved['notes'], '')
        self.assertNotEqual(saved['scope'], self.payload['scope'])
        self.assertEqual(self.client.put(new_url, self.payload, content_type='application/json').status_code, 409)
        self.assertEqual(DocumentStudyNotes.objects.get(user=self.student, version=self.version).notes, self.payload['notes'])

    def test_revoked_membership_blocks_reads_and_writes_without_erasing_notes(self):
        self.prepare_notes()
        self.save_notes()
        CourseMember.objects.filter(pk=self.member_id).update(status='REMOVED')
        self.assertEqual(self.client.get(self.notes_url).status_code, 404)
        self.assertEqual(self.client.put(self.notes_url, self.payload, content_type='application/json').status_code, 404)
        self.assertEqual(DocumentStudyNotes.objects.get(user=self.student, version=self.version).notes, self.payload['notes'])

    def test_reports_persist_and_repeated_autosave_does_not_duplicate_notifications(self):
        self.prepare_notes()
        payload = {**self.payload, 'feedback': {'vote': 'dislike', 'report': {'reason': 'Wrong page', 'opinion': 'Check it'}}}
        self.save_notes(payload)
        count = Notification.objects.filter(kind='MATERIAL_REPORTED').count()
        self.assertEqual(count, 2)
        cache.clear()
        self.save_notes(payload)
        self.assertEqual(Notification.objects.filter(kind='MATERIAL_REPORTED').count(), count)
        payload['feedback']['report']['opinion'] = 'Changed report'
        self.save_notes(payload)
        self.assertEqual(Notification.objects.filter(kind='MATERIAL_REPORTED').count(), count + 2)
        self.assertEqual(self.client.get(self.notes_url).json()['feedback'], payload['feedback'])

    def test_notification_failure_rolls_back_notes_and_report(self):
        self.prepare_notes()
        payload = {**self.payload, 'feedback': {'vote': 'dislike', 'report': {'reason': 'Report', 'opinion': ''}}}
        with patch('apps.notifications.services.notify', side_effect=RuntimeError('fixture failure')):
            with self.assertRaises(RuntimeError):
                self.client.put(self.notes_url, payload, content_type='application/json')
        self.assertFalse(DocumentStudyNotes.objects.exists())
        self.assertEqual(Notification.objects.filter(kind='MATERIAL_REPORTED').count(), 0)

    def test_permission_change_during_validation_rolls_back_write(self):
        self.prepare_notes()
        def revoke(value):
            CourseMember.objects.filter(pk=self.member_id).update(status='REMOVED')
            return value
        with patch('apps.documents.api.study_notes.StudyNotesSerializer.validate', side_effect=revoke):
            self.assertEqual(self.client.put(self.notes_url, self.payload, content_type='application/json').status_code, 404)
        self.assertFalse(DocumentStudyNotes.objects.exists())

    def test_invalid_geometry_or_page_is_rejected_and_unpublished_pdf_is_unavailable(self):
        self.prepare_notes()
        scope = self.payload['scope']
        self.assertEqual(self.client.put(self.notes_url, [], content_type='application/json').status_code, 400)
        for item in [
            {'id': 'a', 'page': 2, 'kind': 'pen', 'points': [[0.1, 0.2]]},
            {'id': 'a', 'page': 1, 'kind': 'pen', 'points': [[-1, 0.2]]},
            {'id': 'a', 'page': 1, 'kind': 'pen', 'points': [['NaN', 0.2]]},
            {'id': 'a', 'page': 1, 'kind': 'text', 'x': 'NaN', 'y': 0.2, 'text': 'Invalid'},
        ]:
            self.assertEqual(self.client.put(self.notes_url, {'items': [item], 'notes': '', 'scope': scope}, content_type='application/json').status_code, 400)
        duplicate = [self.payload['items'][0], self.payload['items'][0]]
        self.assertEqual(self.client.put(self.notes_url, {'items': duplicate, 'notes': '', 'scope': scope}, content_type='application/json').status_code, 400)
        self.login('teacher', 'Teacher123!')
        self.client.patch(self.base + 'publication/', {'is_published': False}, content_type='application/json')
        self.login('student', 'Student123!')
        self.assertEqual(self.client.get(self.notes_url).status_code, 404)


class StudyAnnotationProcessTests(TransactionTestCase):
    setUp = StudyAnnotationTests.setUp
    login = StudyAnnotationTests.login
    upload = StudyAnnotationTests.upload
    upload_file = StudyAnnotationTests.upload_file
    prepare = StudyAnnotationTests.prepare
    publish = StudyAnnotationTests.publish
    prepare_notes = StudyAnnotationTests.prepare_notes
    save_notes = StudyAnnotationTests.save_notes

    def test_fresh_process_reads_and_writes_same_notes_with_same_scope(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Cross-process integration uses the isolated PostgreSQL test database.')
        self.prepare_notes()
        self.save_notes()
        database = connection.settings_dict
        self.assertTrue(database['NAME'].startswith('test_'))
        env = dict(os.environ, DJANGO_SETTINGS_MODULE='config.settings.test', PYTHONDONTWRITEBYTECODE='1',
                   DB_ENGINE=database['ENGINE'], DB_NAME=database['NAME'], DB_HOST=database['HOST'],
                   DB_PORT=str(database['PORT']), DB_USER=database['USER'], DB_PASSWORD=database['PASSWORD'],
                   STUDY_TEST_USER=str(self.student.pk), STUDY_TEST_URL=self.notes_url)
        code = '''import os,json
assert os.environ['DB_NAME'].startswith('test_')
import django
django.setup()
from apps.users.models import User
from common.testing import authenticate_client
from rest_framework.test import APIClient
client=authenticate_client(APIClient(),User.objects.get(pk=os.environ['STUDY_TEST_USER']))
response=client.get(os.environ['STUDY_TEST_URL'])
assert response.status_code==200
payload=response.json()
before=dict(payload)
payload['notes']='Saved by fresh worker'
saved=client.put(os.environ['STUDY_TEST_URL'],payload,format='json')
assert saved.status_code==200
print('STUDY_RESULT_JSON='+json.dumps(before))
'''
        child = subprocess.run([sys.executable, '-B', '-c', code], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(child.returncode, 0, child.stderr)
        result = json.loads(next(line.split('=', 1)[1] for line in child.stdout.splitlines() if line.startswith('STUDY_RESULT_JSON=')))
        self.assertEqual(result, self.payload)
        self.assertEqual(self.client.get(self.notes_url).json()['notes'], 'Saved by fresh worker')
