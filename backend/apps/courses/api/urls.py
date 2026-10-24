from django.urls import path

from .views import CourseDetailView, CourseListCreateView, CourseMemberRevokeView, CourseMembersView
from .enrollment_views import PolicyView, ClassroomsView, ClassroomDetailView, JoinByCodeView, MyJoinRequestsView, MyEnrollmentsView, CancelJoinRequestView, CourseJoinRequestsView, ReviewJoinRequestView
from .enrollment_views import ClassroomEnrollmentsView, ClassroomEnrollmentRevokeView, MyCourseClassroomsView


from .session_views import ClassroomSessionsView, ClassroomSessionDetailView
from .announcement_views import ClassroomAnnouncementsView, ClassroomAnnouncementImageView

from .people_views import ClassroomPeopleView
from .comment_views import AnnouncementCommentsView, AnnouncementCommentDetailView, AnnouncementCommentVoteView, ClassroomCommentMuteView

app_name = "courses"

from .video_views import SessionVideosView, SessionVideoDetailView, SessionVideoFileView, VideoQuestionsView, VideoQuestionDetailView, VideoProgressView, VideoAnswersView, VideoResponsesView, VideoOwnAnswersView

video_prefix = '<uuid:course_id>/classrooms/<uuid:classroom_id>/sessions/<uuid:session_id>/videos/'
video_detail = video_prefix + '<uuid:video_id>/'

from .assessment_views import (AssessmentsView, AssessmentDetailView, AssessmentStartView, AssessmentAttemptView,
    AssessmentSubmitView, AssessmentEventView, AssessmentGradeView, AssessmentFileView,
    AssessmentAssistanceView, AssessmentDashboardView, AssessmentExportView)
assessment_prefix = '<uuid:course_id>/classrooms/<uuid:classroom_id>/sessions/<uuid:session_id>/assessments/'
assessment_detail = assessment_prefix + '<uuid:assessment_id>/'
assessment_attempt = assessment_detail + 'attempts/<uuid:attempt_id>/'

urlpatterns = [
    path(assessment_prefix, AssessmentsView.as_view(), name='assessments'),
    path(assessment_detail, AssessmentDetailView.as_view(), name='assessment'),
    path(assessment_detail + 'start/', AssessmentStartView.as_view(), name='assessment-start'),
    path(assessment_detail + 'assistance/', AssessmentAssistanceView.as_view(), name='assessment-assistance'),
    path(assessment_detail + 'dashboard/', AssessmentDashboardView.as_view(), name='assessment-dashboard'),
    path(assessment_detail + 'export/', AssessmentExportView.as_view(), name='assessment-export'),
    path(assessment_attempt, AssessmentAttemptView.as_view(), name='assessment-attempt'),
    path(assessment_attempt + 'submit/', AssessmentSubmitView.as_view(), name='assessment-submit'),
    path(assessment_attempt + 'events/', AssessmentEventView.as_view(), name='assessment-event'),
    path(assessment_attempt + 'grade/', AssessmentGradeView.as_view(), name='assessment-grade'),
    path(assessment_attempt + 'file/', AssessmentFileView.as_view(), name='assessment-file'),
    path(video_prefix, SessionVideosView.as_view(), name='session-videos'),
    path(video_detail, SessionVideoDetailView.as_view(), name='session-video'),
    path(video_detail + 'file/', SessionVideoFileView.as_view(), name='session-video-file'),
    path(video_detail + 'questions/', VideoQuestionsView.as_view(), name='video-questions'),
    path(video_detail + 'questions/<uuid:question_id>/', VideoQuestionDetailView.as_view(), name='video-question'),
    path(video_detail + 'questions/<uuid:question_id>/answers/', VideoAnswersView.as_view(), name='video-answers'),
    path(video_detail + 'progress/', VideoProgressView.as_view(), name='video-progress'),
    path(video_detail + 'answers/mine/', VideoOwnAnswersView.as_view(), name='video-own-answers'),
    path(video_detail + 'responses/', VideoResponsesView.as_view(), name='video-responses'),
    path('<uuid:course_id>/classrooms/<uuid:classroom_id>/announcements/<uuid:announcement_id>/comments/', AnnouncementCommentsView.as_view(), name='announcement-comments'),
    path('<uuid:course_id>/classrooms/<uuid:classroom_id>/announcements/<uuid:announcement_id>/comments/<uuid:comment_id>/', AnnouncementCommentDetailView.as_view(), name='announcement-comment-delete'),
    path('<uuid:course_id>/classrooms/<uuid:classroom_id>/announcements/<uuid:announcement_id>/comments/<uuid:comment_id>/vote/', AnnouncementCommentVoteView.as_view(), name='announcement-comment-vote'),
    path('<uuid:course_id>/classrooms/<uuid:classroom_id>/comment-mutes/<uuid:user_id>/', ClassroomCommentMuteView.as_view(), name='classroom-comment-mute'),
    path("<uuid:course_id>/classrooms/<uuid:classroom_id>/people/", ClassroomPeopleView.as_view(), name="classroom-people"),
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
