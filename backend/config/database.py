"""One PostgreSQL configuration for local and Docker."""


def database_config(env):
    engine=env.get('DB_ENGINE') or 'django.db.backends.postgresql'
    if engine!='django.db.backends.postgresql':
        raise ValueError('Unsupported database engine.')
    return {'ENGINE':engine,'NAME':env.get('DB_NAME') or env.get('POSTGRES_DB') or 'smart_lms',
        'USER':env.get('DB_USER') or env.get('POSTGRES_USER') or 'smart_lms',
        'PASSWORD':env.get('DB_PASSWORD') or env.get('POSTGRES_PASSWORD') or '',
        'HOST':env.get('DB_HOST') or '127.0.0.1',
        'PORT':env.get('DB_PORT') or env.get('POSTGRES_PORT') or '5432'}
