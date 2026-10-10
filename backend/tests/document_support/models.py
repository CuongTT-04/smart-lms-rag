"""Real owner/membership relations for documents tests only; not product Course."""
import uuid
from django.conf import settings
from django.db import models
class Course(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    teacher=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    title=models.CharField(max_length=200)
class Membership(models.Model):
    course=models.ForeignKey(Course,on_delete=models.CASCADE)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    active=models.BooleanField(default=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["course","user"],name="test_member_unique")]
