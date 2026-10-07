from django.core.exceptions import ValidationError as ModelValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import CourseMember
from apps.courses.permissions import CanManageCourse, CanViewCourse, IsTeacher
from apps.courses.selectors import get_course, list_accessible_courses, list_course_members
from apps.courses.services import (
    create_course, grant_student_access, revoke_student_access, update_course,
)
from common.schema import (
    COURSE_OR_PAGE_NOT_FOUND, CREATE_BAD_REQUEST, FORBIDDEN,
    GRANT_BAD_REQUEST, NOT_FOUND, PAGE_NOT_FOUND, REVOKE_BAD_REQUEST,
    UPDATE_BAD_REQUEST,
)

from .serializers import (
    CourseCreateSerializer, CourseMemberSerializer, CourseSerializer,
    CourseUpdateSerializer, GrantStudentAccessSerializer,
)


@method_decorator(never_cache, name="dispatch")
class CourseListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsTeacher()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CourseCreateSerializer
        return CourseSerializer

    @extend_schema(
        operation_id="courses_list", tags=["Courses"], summary="List accessible courses",
        description=(
            "Paginated (20/page). Teachers see their ACTIVE OWNER memberships in all course states; "
            "students see PUBLISHED courses with ACTIVE STUDENT membership. Admin has no automatic access."
        ),
        responses={200: CourseSerializer(many=True), 403: FORBIDDEN, 404: PAGE_NOT_FOUND},
    )
    def get(self, request):
        courses = list_accessible_courses(user=request.user)
        page = self.paginate_queryset(courses)
        serializer = self.get_serializer(page if page is not None else courses, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @extend_schema(
        operation_id="courses_create", tags=["Courses"], summary="Create a draft course",
        description="Active TEACHER only. Creates the single ACTIVE OWNER membership atomically.",
        request=CourseCreateSerializer,
        responses={201: CourseSerializer, 400: CREATE_BAD_REQUEST, 403: FORBIDDEN},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            course = create_course(actor=request.user, **serializer.validated_data)
        except ModelValidationError as error:
            raise ValidationError(error.message_dict) from error
        return Response(CourseSerializer(course).data, status=status.HTTP_201_CREATED)


@method_decorator(never_cache, name="dispatch")
class CourseManagementView(GenericAPIView):
    permission_classes = [IsAuthenticated, CanManageCourse]

    def get_course(self, course_id):
        course = get_course(course_id=course_id)
        if course is None:
            raise NotFound("Course not found.")
        self.check_object_permissions(self.request, course)
        return course


class CourseDetailView(CourseManagementView):
    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated(), CanViewCourse()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return CourseUpdateSerializer
        return CourseSerializer

    @extend_schema(
        operation_id="courses_retrieve", tags=["Courses"], summary="View an accessible course",
        description="Current account and membership are checked on every request. Revocation takes effect immediately.",
        responses={200: CourseSerializer, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request, course_id):
        course = self.get_course(course_id)
        return Response(self.get_serializer(course).data)

    @extend_schema(
        operation_id="courses_update", tags=["Courses"], summary="Update course information or status",
        description="Only the active global TEACHER with ACTIVE OWNER membership. At least one field required.",
        request=CourseUpdateSerializer,
        responses={200: CourseSerializer, 400: UPDATE_BAD_REQUEST, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def patch(self, request, course_id):
        course = self.get_course(course_id)
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            course = update_course(
                actor=request.user, course=course, changes=serializer.validated_data
            )
        except ModelValidationError as error:
            detail = error.message_dict if hasattr(error, "message_dict") else error.messages
            raise ValidationError(detail) from error
        return Response(CourseSerializer(course).data)


class CourseMembersView(CourseManagementView):
    def get_serializer_class(self):
        if self.request.method == "POST":
            return GrantStudentAccessSerializer
        return CourseMemberSerializer

    @extend_schema(
        operation_id="course_members_list", tags=["Course Members"], summary="List course memberships",
        description="Managers only. Paginated (20/page); includes invited, active, suspended, and removed members.",
        responses={200: CourseMemberSerializer(many=True), 403: FORBIDDEN, 404: COURSE_OR_PAGE_NOT_FOUND},
    )
    def get(self, request, course_id):
        course = self.get_course(course_id)
        members = list_course_members(course=course)
        page = self.paginate_queryset(members)
        serializer = self.get_serializer(page if page is not None else members, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @extend_schema(
        operation_id="course_members_grant", tags=["Course Members"], summary="Grant or restore student access",
        description=(
            "Managers only; target must be an active STUDENT account. Returns 201 for a new membership "
            "or 200 for an existing/restored membership. Cannot replace a non-STUDENT membership."
        ),
        request=GrantStudentAccessSerializer,
        responses={200: CourseMemberSerializer, 201: CourseMemberSerializer,
                   400: GRANT_BAD_REQUEST, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def post(self, request, course_id):
        course = self.get_course(course_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            member, created = grant_student_access(
                actor=request.user, course=course, **serializer.validated_data
            )
        except ModelValidationError as error:
            raise ValidationError(error.message_dict) from error
        return Response(
            CourseMemberSerializer(member).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class CourseMemberRevokeView(CourseManagementView):
    @extend_schema(
        operation_id="course_members_revoke", tags=["Course Members"], summary="Revoke student access",
        description=(
            "Managers only. Use membership UUID, not user UUID. Soft-removes STUDENT membership; "
            "repeated requests return 204. Membership must belong to this course."
        ),
        request=None,
        responses={204: None, 400: REVOKE_BAD_REQUEST, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def delete(self, request, course_id, member_id):
        course = self.get_course(course_id)
        try:
            revoke_student_access(actor=request.user, course=course, member_id=member_id)
        except CourseMember.DoesNotExist as error:
            raise NotFound("Membership not found in this course.") from error
        except ModelValidationError as error:
            raise ValidationError(error.message_dict) from error
        return Response(status=status.HTTP_204_NO_CONTENT)
