from django.urls import path

from .views import CourseDetailView, CourseListCreateView, CourseMemberRevokeView, CourseMembersView


app_name = "courses"

urlpatterns = [
    path("", CourseListCreateView.as_view(), name="create"),
    path("<uuid:course_id>/", CourseDetailView.as_view(), name="update"),
    path("<uuid:course_id>/members/", CourseMembersView.as_view(), name="members"),
    path(
        "<uuid:course_id>/members/<uuid:member_id>/",
        CourseMemberRevokeView.as_view(),
        name="member-revoke",
    ),
]
