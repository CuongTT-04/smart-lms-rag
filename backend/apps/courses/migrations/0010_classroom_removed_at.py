from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('courses', '0009_classroomsession_removed_at')]
    operations = [migrations.AddField(model_name='classroom', name='removed_at', field=models.DateTimeField(blank=True, null=True))]
