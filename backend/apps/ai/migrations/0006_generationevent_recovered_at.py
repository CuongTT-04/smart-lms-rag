from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai', '0005_generation_admission')]

    operations = [
        migrations.AddField(
            model_name='generationevent',
            name='recovered_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
