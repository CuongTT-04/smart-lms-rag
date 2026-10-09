from django.urls import path

from .views import CourseDetailView, CourseListCreateView, CourseMemberRevokeView, CourseMembersView
from .enrollment_views import PolicyView, ClassroomsView, ClassroomDetailView, JoinByCodeView, MyJoinRequestsView, MyEnrollmentsView, CancelJoinRequestView, CourseJoinRequestsView, ReviewJoinRequestView
from .enrollment_views import ClassroomEnrollmentsView, ClassroomEnrollmentRevokeView, MyCourseClassroomsView


from .session_views import ClassroomSessionsView, ClassroomSessionDetailView
from .announcement_views import ClassroomAnnouncementsView, ClassroomAnnouncementImageView

app_name = "courses"

urlpatterns = [
    path("<uuid:course_id>/classrooms/<uuid:classroom_id>/sessions/<uuid:session_id>/", ClassroomSessionDetailView.as_view(), name="classroom-session-update"),
    path("<uuid:course_id>/classrooms/<uuid:classroom_id>/announcements/<uuid:announcement_id>/image/", ClassroomAnnouncementImageView.as_view(), name="classroom-announcement-image"),
    path("<uuid:course_id>/classrooms/<uuid:classroom_id>/announcements/", ClassroomAnnouncementsView.as_view(), name="classroom-announcements"),
    path("<uuid:course_id>/classrooms/<uuid:classroom_id>/sessions/", ClassroomSessionsView.as_view(), name="classroom-sessions"),
    path("join/", JoinByCodeView.as_view(), name="join"),
    path("join-requests/mine/", MyJoinRequestsView.as_view(), name="requests-mine"),
    path("join-requests/<uuid:request_id>/cancel/", CancelJoinRequestView.as_view(), name="request-cancel"),
    path("enrollments/mine/", MyEnrollmentsView.as_view(), name="enrollments-mine"),
    path("", CourseListCreateView.as_view(), name="create"),
    path("<uuid:course_id>/", CourseDetailView.as_view(), name="update"),
    path("<uuid:course_id>/members/", CourseMembersView.as_view(), name="members"),
    path("<uuid:course_id>/access-policy/", PolicyView.as_view(), name="policy"),
    path("<uuid:course_id>/classrooms/", ClassroomsView.as_view(), name="classrooms"),
    path("<uuid:course_id>/classrooms/<uuid:classroom_id>/", ClassroomDetailView.as_view(), name="classroom-update"),
    path("<uuid:course_id>/classrooms/<uuid:classroom_id>/enrollments/", ClassroomEnrollmentsView.as_view(), name="classroom-enrollments"),
    path("<uuid:course_id>/classrooms/<uuid:classroom_id>/enrollments/<uuid:enrollment_id>/", ClassroomEnrollmentRevokeView.as_view(), name="classroom-enrollment-revoke"),
    path("<uuid:course_id>/my-classrooms/", MyCourseClassroomsView.as_view(), name="my-classrooms"),
    path("<uuid:course_id>/join-requests/", CourseJoinRequestsView.as_view(), name="requests"),
    path("<uuid:course_id>/join-requests/<uuid:request_id>/review/", ReviewJoinRequestView.as_view(), name="request-review"),
    path(
        "<uuid:course_id>/members/<uuid:member_id>/",
        CourseMemberRevokeView.as_view(),
        name="member-revoke",
    ),
]
