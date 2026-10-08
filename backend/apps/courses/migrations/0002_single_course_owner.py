from django.db import migrations, models
from django.db.models import Count
from django.utils import timezone


def retire_coteachers(apps, schema_editor):
    Member = apps.get_model("courses", "CourseMember")
    members = Member.objects.using(schema_editor.connection.alias)
    duplicates = members.filter(role="OWNER").values("course_id").annotate(
        count=Count("id")
    ).filter(count__gt=1)
    if duplicates.exists():
        raise RuntimeError("Multiple course owners found. Resolve ownership before migrating.")
    members.filter(role__in=["TEACHER", "ASSISTANT"]).exclude(status="REMOVED").update(
        status="REMOVED", removed_at=timezone.now()
    )


class Migration(migrations.Migration):
    dependencies = [("courses", "0001_initial")]

    operations = [
        migrations.RunPython(retire_coteachers, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="coursemember",
            constraint=models.UniqueConstraint(
                fields=("course",), condition=models.Q(role="OWNER"),
                name="courses_single_owner",
            ),
        ),
        migrations.AddConstraint(
            model_name="coursemember",
            constraint=models.CheckConstraint(
                condition=models.Q(role__in=["OWNER", "STUDENT"]) | models.Q(status="REMOVED"),
                name="courses_no_coteachers",
            ),
        ),
    ]
