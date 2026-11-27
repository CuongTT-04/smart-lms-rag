import csv
from io import BytesIO, StringIO
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.users.institutions import import_institutions, save_institution
from apps.users.models import Institution, User
from common.testing import authenticate_client


class InstitutionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser('catalog_admin', password='Catalog-Admin-839!')
        self.client = authenticate_client(APIClient(), self.admin)
        self.row = dict(code='test-ptit', name='Học viện Công nghệ Bưu chính Viễn thông',
                        aliases=['PTIT', 'BCVT'], province='Hà Nội', campus='Cơ sở kiểm thử',
                        levels=['UNIVERSITY'], source_url='https://ptit.edu.vn/',
                        source_checked_at='2026-11-27', active=True)
        self.school = save_institution(actor=self.admin, values=self.row)

    def upload(self, rows=None, *, filename='schools.csv'):
        rows = rows if rows is not None else [self.row]
        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(self.row))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: '|'.join(v) if isinstance(v, list) else str(v).lower() if isinstance(v, bool) else v
                             for k, v in row.items()})
        return SimpleUploadedFile(filename, stream.getvalue().encode('utf-8-sig'))

    def test_public_search_is_accent_insensitive_filtered_bounded_and_minimal(self):
        client = APIClient()
        for query in ['ptit', 'BCVT', 'BUU CHINH', 'Bưu chính']:
            response = client.get('/api/users/institutions/', {'q': query, 'province': 'ha noi', 'level': 'UNIVERSITY'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['results'][0]['id'], str(self.school.pk))
            self.assertEqual(set(response.data['results'][0]), {'id', 'name', 'aliases', 'province', 'campus', 'levels'})
        self.assertEqual(client.get('/api/users/institutions/', {'level': 'PRIMARY'}).data['results'], [])
        self.assertEqual(client.get('/api/users/institutions/', {'q': 'x' * 101}).status_code, 400)
        self.assertEqual(client.get('/api/users/institutions/', {'limit': '1000'}).status_code, 400)
        self.assertEqual(client.get('/api/users/institutions/', {'level': 'UNKNOWN'}).status_code, 400)

    def test_search_pagination_has_at_most_twenty_results(self):
        for i in range(23):
            save_institution(actor=self.admin, values={**self.row, 'code': f'page-{i}', 'name': f'Trường {i}'})
        client = APIClient()
        result = client.get('/api/users/institutions/').data
        self.assertEqual(len(result['results']), 20)
        self.assertTrue(result['has_more'])
        result = client.get('/api/users/institutions/', {'offset': 20}).data
        self.assertEqual(len(result['results']), 4)
        self.assertFalse(result['has_more'])

    @patch('apps.users.api.institution_views.check_and_increment', return_value=(False, 60))
    def test_lookup_is_rate_limited(self, _counter):
        response = APIClient().get('/api/users/institutions/')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '60')

    def test_inactive_school_not_selectable_but_existing_relation_survives(self):
        teacher = User.objects.create_user('existing_teacher', role='TEACHER')
        teacher.teacher_profile.institution = self.school
        teacher.teacher_profile.save()
        save_institution(actor=self.admin, institution_id=self.school.pk, values={'active': False})
        self.assertEqual(APIClient().get('/api/users/institutions/').data['results'], [])
        teacher.teacher_profile.refresh_from_db()
        self.assertEqual(teacher.teacher_profile.institution_id, self.school.pk)
        with self.assertRaises(ProtectedError):
            self.school.delete()

    def test_duplicate_normalized_identity_rejected_but_different_campus_allowed(self):
        with self.assertRaises(ValidationError):
            save_institution(actor=self.admin, values={**self.row, 'code': 'duplicate',
                             'name': 'Hoc vien Cong nghe Buu chinh Vien thong'})
        other = save_institution(actor=self.admin, values={**self.row, 'code': 'another', 'campus': 'Cơ sở khác'})
        self.assertNotEqual(other.pk, self.school.pk)

    def test_multilevel_and_invalid_source_schema(self):
        obj = save_institution(actor=self.admin, values={**self.row, 'code': 'multi', 'name': 'Liên cấp',
                                                       'levels': ['PRIMARY', 'LOWER_SECONDARY', 'UPPER_SECONDARY']})
        self.assertEqual(len(obj.levels), 3)
        for changes in [{'levels': ['WRONG']}, {'source_url': 'javascript:alert(1)'},
                        {'aliases': 'PTIT'}, {'source_checked_at': '2099-01-01'}, {'code': 'other-code'}]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                save_institution(actor=self.admin, institution_id=obj.pk, values=changes)

    def test_admin_api_checks_live_role_and_model_permissions(self):
        self.assertEqual(APIClient().post('/api/operations/institutions/', {}, format='json').status_code, 401)
        teacher = User.objects.create_user('not_admin', role='TEACHER')
        client = authenticate_client(APIClient(), teacher)
        self.assertEqual(client.post('/api/operations/institutions/', self.row, format='json').status_code, 403)
        admin = User.objects.create_user('limited_admin', role='ADMIN')
        client = authenticate_client(APIClient(), admin)
        self.assertEqual(client.get('/api/operations/institutions/').status_code, 403)
        admin.user_permissions.add(Permission.objects.get(codename='view_institution'))
        self.assertEqual(client.get('/api/operations/institutions/').status_code, 200)
        self.assertEqual(client.patch(f'/api/operations/institutions/{self.school.pk}/', {'active': False}, format='json').status_code, 403)
        User.objects.filter(pk=self.admin.pk).update(status='BLOCKED', is_active=False)
        with self.assertRaises(PermissionError):
            save_institution(actor=self.admin, values={**self.row, 'code': 'blocked'})

    def test_admin_create_update_and_no_delete(self):
        response = self.client.post('/api/operations/institutions/', {**self.row, 'code': 'new', 'name': 'Trường mới'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        url = f"/api/operations/institutions/{response.data['id']}/"
        self.assertEqual(self.client.patch(url, {'active': False}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 405)

    def test_import_dry_run_apply_repeat_and_invalid_batch_is_atomic(self):
        new = {**self.row, 'code': 'imported', 'name': 'Trường nhập'}
        preview = import_institutions(actor=self.admin, upload=self.upload([new]), dry_run=True)
        self.assertTrue(preview['valid'])
        self.assertEqual(preview['created'], 1)
        self.assertFalse(Institution.objects.filter(code='imported').exists())
        applied = import_institutions(actor=self.admin, upload=self.upload([new]), dry_run=False)
        self.assertEqual(applied['created'], 1)
        self.assertEqual(import_institutions(actor=self.admin, upload=self.upload([new]), dry_run=False)['unchanged'], 1)
        bad = {**new, 'code': 'bad', 'name': 'Trường lỗi', 'source_url': 'not a URL'}
        result = import_institutions(actor=self.admin, upload=self.upload([{**new, 'code': 'not-written', 'name': 'Không ghi'}, bad]), dry_run=False)
        self.assertFalse(result['valid'])
        self.assertFalse(result['applied'])
        self.assertFalse(Institution.objects.filter(code='not-written').exists())
        self.assertEqual(result['errors'][0]['row'], 3)

    def test_import_duplicates_and_unknown_headers_rejected(self):
        result = import_institutions(actor=self.admin, upload=self.upload([self.row, self.row]), dry_run=True)
        self.assertFalse(result['valid'])
        with self.assertRaises(ValidationError):
            import_institutions(actor=self.admin, upload=SimpleUploadedFile('bad.csv', b'code,name,unexpected\nx,y,z\n'), dry_run=True)

    def test_xlsx_import_and_formulas_rejected(self):
        from openpyxl import Workbook
        def xlsx(formula=False):
            book = Workbook(); sheet = book.active
            sheet.append(list(self.row))
            row = {**self.row, 'name': '=1+1' if formula else 'Trường XLSX', 'code': 'xlsx'}
            sheet.append(['|'.join(v) if isinstance(v, list) else v for v in row.values()])
            stream = BytesIO(); book.save(stream)
            return SimpleUploadedFile('schools.xlsx', stream.getvalue())
        self.assertEqual(import_institutions(actor=self.admin, upload=xlsx(), dry_run=False)['created'], 1)
        with self.assertRaises(ValidationError):
            import_institutions(actor=self.admin, upload=xlsx(True), dry_run=True)

    def test_import_api_defaults_to_preview_and_rejects_invalid_boolean(self):
        url = '/api/operations/institutions/import/'
        self.assertEqual(self.client.post(url, {'file': self.upload()}, format='multipart').status_code, 200)
        self.assertEqual(self.client.post(url, {'file': self.upload(), 'dry_run': 'maybe'}, format='multipart').status_code, 400)

    def test_import_size_row_limits_and_invalid_workbook(self):
        for upload in [SimpleUploadedFile('large.csv', b'x' * (2 * 1024 * 1024 + 1)),
                       self.upload([self.row] * 501), SimpleUploadedFile('broken.xlsx', b'not a zip')]:
            with self.subTest(name=upload.name), self.assertRaises(ValidationError):
                import_institutions(actor=self.admin, upload=upload, dry_run=True)

    def test_import_rechecks_permissions_and_reports_update_without_writing_preview(self):
        updated = {**self.row, 'name': 'Tên trường đã sửa'}
        report = import_institutions(actor=self.admin, upload=self.upload([updated]), dry_run=True)
        self.assertEqual(report['updated'], 1)
        self.school.refresh_from_db(); self.assertEqual(self.school.name, self.row['name'])
        self.assertEqual(import_institutions(actor=self.admin, upload=self.upload([updated]), dry_run=False)['updated'], 1)
        limited = User.objects.create_user('import_reader', role='ADMIN')
        limited.user_permissions.add(Permission.objects.get(codename='view_institution'))
        with self.assertRaises(PermissionError):
            import_institutions(actor=limited, upload=self.upload(), dry_run=True)

    def test_django_admin_uses_validated_form_and_keeps_stable_code(self):
        from apps.users.admin import InstitutionForm
        values = {**self.row, 'aliases': '["PTIT"]', 'levels': '["UNIVERSITY"]'}
        values.update(code='admin-form', name='Trường từ Django Admin')
        form = InstitutionForm(data=values)
        self.assertTrue(form.is_valid(), form.errors)
        values['source_checked_at'] = '2099-01-01'
        self.assertFalse(InstitutionForm(data=values).is_valid())

    def test_registration_service_revalidates_deactivated_institution(self):
        from apps.users.services import register_user
        save_institution(actor=self.admin, institution_id=self.school.pk, values={'active': False})
        with self.assertRaises(ValidationError):
            register_user(username='direct', email='direct@example.com', password='Institution-Test-839!',
                          full_name='Teacher', role='TEACHER', institution_id=self.school.pk)
        self.assertFalse(User.objects.filter(username='direct').exists())

    def test_seed_twice_does_not_duplicate_or_overwrite_admin_edits(self):
        call_command('seed_institutions', stdout=StringIO())
        self.assertEqual(Institution.objects.count(), 8)
        seeded = Institution.objects.get(code='hanoi-ptit')
        save_institution(actor=self.admin, institution_id=seeded.pk, values={'active': False})
        call_command('seed_institutions', stdout=StringIO())
        self.assertEqual(Institution.objects.count(), 8)
        seeded.refresh_from_db(); self.assertFalse(seeded.active)

    def test_teacher_registration_requires_exactly_one_valid_institution_choice(self):
        base = dict(username='registered', email='registered@example.com', full_name='Teacher', role='TEACHER',
                    password='Institution-Test-839!', password_confirm='Institution-Test-839!')
        client = APIClient()
        for choice in [{}, {'institution_id': 'bad'}, {'institution_id': str(self.school.pk), 'institution_other_name': 'Other'}]:
            self.assertEqual(client.post('/api/users/register/', {**base, **choice}, format='json').status_code, 400)
        response = client.post('/api/users/register/', {**base, 'institution_id': str(self.school.pk)}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username='registered')
        self.assertEqual(user.teacher_profile.institution_id, self.school.pk)
        self.assertFalse(user.email_verified)
        self.assertFalse(user.is_staff)
        self.assertEqual(response.data['user']['teacher_profile']['institution']['id'], str(self.school.pk))

    def test_other_name_not_inserted_in_catalog_student_rejected_and_inactive_denied(self):
        base = dict(username='other', email='other@example.com', full_name='Teacher', role='TEACHER',
                    password='Institution-Test-839!', password_confirm='Institution-Test-839!')
        client = APIClient(); count = Institution.objects.count()
        response = client.post('/api/users/register/', {**base, 'institution_other_name': '  Trường tự khai  '}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get(username='other').teacher_profile.institution_other_name, 'Trường tự khai')
        self.assertEqual(Institution.objects.count(), count)
        payload = {**base, 'username': 'student', 'email': 'student@example.com', 'role': 'STUDENT', 'institution_id': str(self.school.pk)}
        self.assertEqual(client.post('/api/users/register/', payload, format='json').status_code, 400)
        save_institution(actor=self.admin, institution_id=self.school.pk, values={'active': False})
        self.assertEqual(client.post('/api/users/register/', {**base, 'username': 'inactive', 'email': 'inactive@example.com', 'institution_id': str(self.school.pk)}, format='json').status_code, 400)
