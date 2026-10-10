from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('courses', '0008_classroomsession_is_draft')]
    operations = [migrations.AddField(model_name='classroomsession', name='removed_at', field=models.DateTimeField(null=True, blank=True))]
