from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('courses', '0007_classroomannouncement_image_and_more')]
    operations = [migrations.AddField(model_name='classroomsession', name='is_draft', field=models.BooleanField(default=True))]
