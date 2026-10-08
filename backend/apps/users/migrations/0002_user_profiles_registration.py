import uuid

from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower
import django.core.validators
import django.db.models.deletion


def backfill_profiles(apps, schema_editor):
    User = apps.get_model("users", "User")
    Student = apps.get_model("users", "StudentProfile")
    Teacher = apps.get_model("users", "TeacherProfile")
    alias = schema_editor.connection.alias
    users = User.objects.using(alias)
    for field in ("username", "email"):
        candidates = users.exclude(email="") if field == "email" else users
        duplicates = candidates.annotate(identifier=Lower(field)).values("identifier").annotate(
            count=Count("id")
        ).filter(count__gt=1)
        if duplicates.exists():
            raise RuntimeError(f"Duplicate {field} identifiers found; resolve them before migrating.")
    for user in users.iterator():
        Student.objects.using(alias).get_or_create(user_id=user.pk)
        Teacher.objects.using(alias).get_or_create(user_id=user.pk)


class Migration(migrations.Migration):
    dependencies = [("users", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="user", name="avatar_url",
            field=models.URLField(blank=True, default="", db_default="", max_length=2048),
        ),
        migrations.AddField(
            model_name="user", name="phone",
            field=models.CharField(blank=True, default="", db_default="", max_length=20, validators=[
                django.core.validators.RegexValidator(r"^\+?[0-9]{8,15}$", "Enter 8-15 digits with an optional leading +.")
            ]),
        ),
        migrations.CreateModel(
            name="StudentProfile",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("learning_goal", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(to="users.user", on_delete=django.db.models.deletion.CASCADE, related_name="student_profile")),
            ],
        ),
        migrations.CreateModel(
            name="TeacherProfile",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("bio", models.TextField(blank=True, default="")),
                ("specialization", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(to="users.user", on_delete=django.db.models.deletion.CASCADE, related_name="teacher_profile")),
            ],
        ),
        migrations.RunPython(backfill_profiles, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(Lower("username"), name="users_unique_username_ci"),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(Lower("email"), condition=~models.Q(email=""), name="users_unique_email_ci"),
        ),
    ]
