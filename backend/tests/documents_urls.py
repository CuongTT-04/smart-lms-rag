from django.urls import include,path
from apps.documents.api.urls import course_urlpatterns
urlpatterns=[path("api/documents/",include("apps.documents.api.urls")),
             path("api/courses/<uuid:course_id>/documents/",include((course_urlpatterns,"course-documents")))]
