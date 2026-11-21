import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('ai', '0002_chat_conversations'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name='SummaryTask', fields=[
        ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
        ('client_request_id', models.UUIDField(default=uuid.uuid4)),
        ('selector', models.JSONField()), ('state', models.JSONField()),
        ('result', models.JSONField(null=True, blank=True)),
        ('status', models.CharField(max_length=10, default='PENDING', choices=[(s, s) for s in ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')])),
        ('lease_token', models.UUIDField(null=True)), ('lease_expires_at', models.DateTimeField(null=True)),
        ('error_code', models.CharField(max_length=48, blank=True)),
        ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
        ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
        ('document', models.ForeignKey(to='documents.knowledgedocument', on_delete=django.db.models.deletion.CASCADE)),
        ('version', models.ForeignKey(to='documents.documentversion', on_delete=django.db.models.deletion.CASCADE)),
    ], options={'constraints': [models.UniqueConstraint(fields=('user', 'client_request_id'), name='ai_summary_request_once')]})]
