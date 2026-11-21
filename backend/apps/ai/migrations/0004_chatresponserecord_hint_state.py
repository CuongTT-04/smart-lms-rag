from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai', '0003_summarytask')]
    operations = [migrations.AddField(
        model_name='chatresponserecord', name='hint_state',
        field=models.JSONField(blank=True, null=True))]
