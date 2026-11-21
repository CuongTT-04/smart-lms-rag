import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('documents', '0003_knowledgedocument_session'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentStudyNotes',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('items', models.JSONField(default=list)),
                ('notes', models.TextField(blank=True, default='')),
                ('feedback', models.JSONField(blank=True, default=dict)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_study_notes', to=settings.AUTH_USER_MODEL)),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='study_notes', to='documents.documentversion')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('user', 'version'), name='doc_study_user_version_unique')],
            },
        ),
    ]
