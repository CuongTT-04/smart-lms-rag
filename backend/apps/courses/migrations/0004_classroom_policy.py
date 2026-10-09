from django.db import migrations, models


def preserve_policy(apps, schema_editor):
    Classroom = apps.get_model('courses', 'Classroom')
    Policy = apps.get_model('courses', 'AccessPolicy')
    alias = schema_editor.connection.alias
    for policy in Policy.objects.using(alias).all().iterator():
        Classroom.objects.using(alias).filter(course_id=policy.course_id).update(visibility=policy.visibility, require_approval=policy.require_approval)


class Migration(migrations.Migration):
    dependencies = [('courses', '0003_accesspolicy_classroom_enrollment_joinrequest_and_more')]
    operations = [
        migrations.AddField(model_name='classroom', name='visibility', field=models.CharField(max_length=7, choices=[('PUBLIC', 'Public'), ('PRIVATE', 'Private')], default='PRIVATE')),
        migrations.AddField(model_name='classroom', name='require_approval', field=models.BooleanField(default=False)),
        migrations.RunPython(preserve_policy, migrations.RunPython.noop),
    ]
