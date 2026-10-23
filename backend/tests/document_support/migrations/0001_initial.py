import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial=True
    dependencies=[migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name='Course',fields=[
            ('id',models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
            ('title',models.CharField(max_length=200)),
            ('teacher',models.ForeignKey(to=settings.AUTH_USER_MODEL,on_delete=django.db.models.deletion.PROTECT))]),
        migrations.CreateModel(name='Membership',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('active',models.BooleanField(default=True)),
            ('course',models.ForeignKey(to='document_test_support.course',on_delete=django.db.models.deletion.CASCADE)),
            ('user',models.ForeignKey(to=settings.AUTH_USER_MODEL,on_delete=django.db.models.deletion.CASCADE))],
            options={'constraints':[models.UniqueConstraint(fields=('course','user'),name='test_member_unique')]})]
