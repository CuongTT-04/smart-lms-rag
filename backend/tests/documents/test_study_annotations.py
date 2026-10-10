from tests.documents import test_material_access as material
from django.test import TestCase


class StudyAnnotationTests(TestCase):
    setUp = material.MaterialAccessTests.setUp
    login = material.MaterialAccessTests.login
    upload = material.MaterialAccessTests.upload
    upload_file = material.MaterialAccessTests.upload_file
    prepare = material.MaterialAccessTests.prepare
    publish = material.MaterialAccessTests.publish

    def test_annotations_are_private_and_can_be_read_back_until_server_memory_resets(self):
        self.prepare(); self.publish()
        url = self.base + f'study-notes/?version_id={self.version.pk}'
        self.login('student', 'Student123!')
        payload = {'items': [{'id': 'a', 'page': 1, 'kind': 'pen', 'points': [[0.1, 0.2], [0.3, 0.4]]}], 'notes': 'My note'}
        payload['scope'] = self.client.get(url).json()['scope']
        payload['feedback'] = {'vote': 'like', 'report': {'reason': 'Incorrect page', 'opinion': 'Please review'}}
        self.assertEqual(self.client.put(url, payload, content_type='application/json').status_code, 200)
        self.assertEqual(self.client.get(url).json(), payload)
        self.login('teacher', 'Teacher123!')
        self.assertEqual(self.client.get(url).json()['items'], [])
        self.assertEqual(self.client.put(url, payload, content_type='application/json').status_code, 409)
        self.login('other', 'Teacher123!')
        self.assertEqual(self.client.get(url).status_code, 404)
        from apps.documents.api.study_notes import study_cache
        study_cache.clear()
        self.login('student', 'Student123!')
        self.assertEqual(self.client.get(url).json()['items'], [])
        from unittest.mock import patch
        with patch('apps.documents.api.study_notes.study_session', 'new-docker-session'):
            self.assertEqual(self.client.put(url, payload, content_type='application/json').status_code, 409)

    def test_invalid_geometry_or_page_is_rejected_and_unpublished_pdf_is_unavailable(self):
        self.prepare(); self.publish()
        url = self.base + f'study-notes/?version_id={self.version.pk}'
        self.login('student', 'Student123!')
        scope = self.client.get(url).json()['scope']
        for item in [
            {'id': 'a', 'page': 2, 'kind': 'pen', 'points': [[0.1, 0.2]]},
            {'id': 'a', 'page': 1, 'kind': 'pen', 'points': [[-1, 0.2]]},
        ]:
            self.assertEqual(self.client.put(url, {'items': [item], 'notes': '', 'scope': scope}, content_type='application/json').status_code, 400)
        self.login('teacher', 'Teacher123!')
        self.client.patch(self.base + 'publication/', {'is_published': False}, content_type='application/json')
        self.login('student', 'Student123!')
        self.assertEqual(self.client.get(url).status_code, 404)
