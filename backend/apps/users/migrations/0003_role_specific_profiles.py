from django.db import migrations


def align_profiles(apps, schema_editor):
    User = apps.get_model("users", "User")
    Student = apps.get_model("users", "StudentProfile")
    Teacher = apps.get_model("users", "TeacherProfile")
    alias = schema_editor.connection.alias
    students = Student.objects.using(alias).exclude(user__role="STUDENT")
    teachers = Teacher.objects.using(alias).exclude(user__role="TEACHER")
    if students.exclude(learning_goal="").exists() or teachers.exclude(bio="", specialization="").exists():
        raise RuntimeError("Nonempty profiles conflict with user roles. Back up and resolve them before migrating.")
    students.delete()
    teachers.delete()
    for user in User.objects.using(alias).filter(role__in=["STUDENT", "TEACHER"]).iterator():
        profile = Student if user.role == "STUDENT" else Teacher
        profile.objects.using(alias).get_or_create(user_id=user.pk)


class Migration(migrations.Migration):
    dependencies = [("users", "0002_user_profiles_registration")]

    operations = [migrations.RunPython(align_profiles, migrations.RunPython.noop)]
