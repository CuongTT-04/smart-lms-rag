from django.test import SimpleTestCase
from config.database import database_config


class DatabaseConfigTests(SimpleTestCase):
    def test_default_is_postgresql_not_sqlite(self):
        result=database_config({})
        self.assertEqual(result['ENGINE'],'django.db.backends.postgresql')
        self.assertEqual(result['NAME'],'smart_lms')
        self.assertEqual(result['HOST'],'127.0.0.1')

    def test_docker_settings_override_local_postgres_defaults(self):
        result=database_config({'DB_HOST':'database','DB_PORT':'5432','DB_NAME':'demo','DB_USER':'demo','DB_PASSWORD':'secret'})
        self.assertEqual((result['HOST'],result['PORT'],result['NAME']),('database','5432','demo'))
        self.assertEqual(result['PASSWORD'],'secret')

    def test_postgres_compose_variables_are_shared_with_local(self):
        result=database_config({'POSTGRES_DB':'shared','POSTGRES_USER':'shared','POSTGRES_PASSWORD':'secret','POSTGRES_PORT':'5433'})
        self.assertEqual((result['NAME'],result['USER'],result['PASSWORD'],result['PORT']),('shared','shared','secret','5433'))

    def test_sqlite_is_rejected_even_with_an_explicit_path(self):
        with self.assertRaises(ValueError):database_config({'DB_ENGINE':'django.db.backends.sqlite3'})
        with self.assertRaises(ValueError):database_config({'DB_ENGINE':'django.db.backends.sqlite3','DB_NAME':':memory:'})
