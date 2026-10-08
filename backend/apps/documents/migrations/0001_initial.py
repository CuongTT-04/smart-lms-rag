import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        (getattr(settings, 'DOCUMENTS_COURSE_MODEL', 'courses.Course').split('.')[0], '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentVersion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('version_number', models.PositiveIntegerField()),
                ('file_name', models.CharField(max_length=255)),
                ('file_type', models.CharField(default='PDF', max_length=10)),
                ('original_storage_key', models.CharField(max_length=255)),
                ('file_size_bytes', models.PositiveBigIntegerField()),
                ('checksum_sha256', models.CharField(max_length=64)),
                ('page_count', models.PositiveIntegerField()),
                ('extracted_storage_key', models.CharField(blank=True, default='', max_length=255)),
                ('watermarked_view_key', models.CharField(blank=True, default='', max_length=255)),
                ('watermark_status', models.CharField(default='NOT_STARTED', max_length=20)),
                ('status', models.CharField(choices=[('QUEUED', 'QUEUED'), ('PROCESSING', 'PROCESSING'), ('EXTRACTED', 'EXTRACTED'), ('READY', 'READY'), ('FAILED', 'FAILED'), ('REMOVED', 'REMOVED')], default='QUEUED', max_length=20)),
                ('ocr_used', models.BooleanField(default=False)),
                ('extracted_at', models.DateTimeField(blank=True, null=True)),
                ('indexed_at', models.DateTimeField(blank=True, null=True)),
                ('removed_at', models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='IngestionJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('job_type', models.CharField(default='EXTRACT', max_length=20)),
                ('idempotency_key', models.CharField(max_length=64, unique=True)),
                ('payload_digest', models.CharField(max_length=64)),
                ('status', models.CharField(choices=[('QUEUED', 'QUEUED'), ('RUNNING', 'RUNNING'), ('SUCCEEDED', 'SUCCEEDED'), ('FAILED', 'FAILED'), ('CANCELLED', 'CANCELLED')], default='QUEUED', max_length=20)),
                ('attempt_count', models.PositiveIntegerField(default=0)),
                ('worker_token', models.UUIDField(blank=True, null=True)),
                ('lease_expires_at', models.DateTimeField(blank=True, null=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('error_code', models.CharField(blank=True, default='', max_length=64)),
                ('document_version', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='jobs', to='documents.documentversion')),
            ],
        ),
        migrations.CreateModel(
            name='KnowledgeDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('title', models.CharField(max_length=255)),
                ('material_policy', models.CharField(choices=[('PROTECTED', 'Protected'), ('PUBLIC_DOWNLOAD', 'Public download')], default='PROTECTED', max_length=20)),
                ('policy_revision', models.PositiveIntegerField(default=1)),
                ('is_published', models.BooleanField(default=False)),
                ('removed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('active_version', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='active_for_documents', to='documents.documentversion')),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='learning_documents', to=getattr(settings, 'DOCUMENTS_COURSE_MODEL', 'courses.Course'))),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='uploaded_documents', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='documentversion',
            name='document',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='versions', to='documents.knowledgedocument'),
        ),
        migrations.CreateModel(
            name='DocumentOperation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('action', models.CharField(max_length=20)),
                ('client_key', models.CharField(max_length=128)),
                ('payload_digest', models.CharField(max_length=64)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=getattr(settings, 'DOCUMENTS_COURSE_MODEL', 'courses.Course'))),
                ('version', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='documents.documentversion')),
                ('job', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='documents.ingestionjob')),
                ('document', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='documents.knowledgedocument')),
            ],
        ),
        migrations.AddIndex(
            model_name='ingestionjob',
            index=models.Index(fields=['status', 'created_at'], name='doc_job_queue_idx'),
        ),
        migrations.AddIndex(
            model_name='knowledgedocument',
            index=models.Index(fields=['course', 'removed_at', 'is_published'], name='doc_course_scope_idx'),
        ),
        migrations.AddConstraint(
            model_name='documentversion',
            constraint=models.UniqueConstraint(fields=('document', 'version_number'), name='doc_version_number_unique'),
        ),
        migrations.AddConstraint(
            model_name='documentversion',
            constraint=models.CheckConstraint(condition=models.Q(('version_number__gte', 1)), name='doc_version_positive'),
        ),
        migrations.AddConstraint(
            model_name='documentversion',
            constraint=models.CheckConstraint(condition=models.Q(('file_size_bytes__gt', 0)), name='doc_size_positive'),
        ),
        migrations.AddConstraint(
            model_name='documentoperation',
            constraint=models.UniqueConstraint(fields=('actor', 'course', 'action', 'client_key'), name='doc_request_idempotent'),
        ),
    ]
