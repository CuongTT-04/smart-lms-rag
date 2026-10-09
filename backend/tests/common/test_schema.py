from django.contrib.staticfiles import finders
from django.test import SimpleTestCase
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema
from rest_framework.test import APIClient

from apps.courses.models import Course, CourseMember, Enrollment, JoinRequest
from apps.users.models import User


class OpenAPITests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schema = SchemaGenerator().get_schema(request=None, public=True)

    def component(self, reference):
        if "allOf" in reference:
            reference = reference["allOf"][0]
        return self.schema["components"]["schemas"][reference["$ref"].rsplit("/", 1)[-1]]

    def test_schema_validates_and_documents_all_business_operations(self):
        validate_schema(self.schema)
        expected = {
            ("/api/health/", "get"),
            ("/api/users/register/", "post"),
            ("/api/users/login/", "post"),
            ("/api/users/password-reset/", "post"),
            ("/api/users/password-reset/confirm/", "post"),
            ("/api/users/token/refresh/", "post"),
            ("/api/users/session/", "get"),
            ("/api/users/logout/", "post"),
            ("/api/users/me/", "get"),
            ("/api/users/me/", "patch"),
            ("/api/users/me/avatar/", "post"),
            ("/api/courses/", "get"),
            ("/api/courses/", "post"),
            ("/api/courses/{course_id}/", "get"),
            ("/api/courses/{course_id}/", "patch"),
            ("/api/courses/{course_id}/members/", "get"),
            ("/api/courses/join/", "post"),
            ("/api/courses/join-requests/mine/", "get"),
            ("/api/courses/join-requests/{request_id}/cancel/", "post"),
            ("/api/courses/enrollments/mine/", "get"),
            ("/api/courses/{course_id}/access-policy/", "get"),
            ("/api/courses/{course_id}/access-policy/", "patch"),
            ("/api/courses/{course_id}/classrooms/", "get"),
            ("/api/courses/{course_id}/classrooms/", "post"),
            ("/api/courses/{course_id}/classrooms/{classroom_id}/", "patch"),
            ("/api/courses/{course_id}/classrooms/{classroom_id}/enrollments/", "get"),
            ("/api/courses/{course_id}/classrooms/{classroom_id}/enrollments/{enrollment_id}/", "delete"),
            ("/api/courses/{course_id}/my-classrooms/", "get"),
            ("/api/courses/{course_id}/join-requests/", "get"),
            ("/api/courses/{course_id}/join-requests/{request_id}/review/", "post"),
            ("/api/courses/{course_id}/members/{member_id}/", "delete"),
        }
        expected.update({
            ("/api/documents/{document_id}/publication/", "patch"),
            ("/api/documents/{document_id}/policy/", "patch"),
            ("/api/documents/{document_id}/view/", "get"),
            ("/api/documents/{document_id}/download/", "get"),
            ("/api/courses/{course_id}/documents/", "get"),
            ("/api/courses/{course_id}/documents/", "post"),
            ("/api/documents/{document_id}/status/", "get"),
            ("/api/documents/{document_id}/versions/", "post"),
            ("/api/documents/{document_id}/retry/", "post"),
            ("/api/documents/{document_id}/extraction/", "get"),
            ("/api/documents/{document_id}/", "delete"),
        })
        expected.add(("/api/courses/{course_id}/classrooms/{classroom_id}/sessions/{session_id}/", "patch"))
        expected.add(("/api/courses/{course_id}/classrooms/{classroom_id}/announcements/{announcement_id}/image/", "get"))
        expected.update({("/api/courses/{course_id}/classrooms/{classroom_id}/announcements/", "get"), ("/api/courses/{course_id}/classrooms/{classroom_id}/announcements/", "post")})
        expected.update({("/api/courses/{course_id}/classrooms/{classroom_id}/sessions/", "get"), ("/api/courses/{course_id}/classrooms/{classroom_id}/sessions/", "post")})
        actual = {(path, method) for path, methods in self.schema["paths"].items() for method in methods}
        expected.add(("/api/documents/{document_id}/", "patch"))
        expected.add(("/api/courses/{course_id}/classrooms/{classroom_id}/sessions/{session_id}/", "delete"))
        self.assertEqual(actual, expected)
        ids = [operation["operationId"] for methods in self.schema["paths"].values() for operation in methods.values()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_jwt_security_and_public_authentication_endpoints_are_documented(self):
        scheme = self.schema["components"]["securitySchemes"]["jwtAuth"]
        self.assertEqual(scheme["type"], "http")
        self.assertEqual(scheme["scheme"], "bearer")
        self.assertEqual(scheme["bearerFormat"], "JWT")
        public = {"/api/health/", "/api/users/register/", "/api/users/login/", "/api/users/password-reset/", "/api/users/password-reset/confirm/", "/api/users/token/refresh/", "/api/users/session/"}
        for path, methods in self.schema["paths"].items():
            for operation in methods.values():
                if path in public:
                    self.assertFalse(operation.get("security"))
                else:
                    self.assertEqual(operation["security"], [{"jwtAuth": []}])

    def test_swagger_groups_and_operations_follow_endpoint_index(self):
        self.assertEqual(
            [tag["name"] for tag in self.schema["tags"]],
            ["System", "Authentication", "Courses", "Course Members", "Enrollment"],
        )
        operations = [
            operation["operationId"]
            for tag in self.schema["tags"]
            for methods in self.schema["paths"].values()
            for operation in methods.values()
            if tag["name"] in operation["tags"]
        ]
        self.assertEqual(operations[:17], [
            "health_check", "users_register", "users_login", "users_password_reset_request", "users_password_reset_confirm", "users_token_refresh", "users_session", "users_logout", "users_me", "users_update_me", "users_upload_avatar",
            "courses_list", "courses_create", "courses_retrieve", "courses_update",
            "course_members_list", "course_members_revoke",
        ])
        self.assertEqual(set(operations[17:]), {"classrooms_join", "join_requests_mine", "join_requests_cancel", "enrollments_mine", "course_policy_retrieve", "course_policy_update", "classrooms_list", "classrooms_create", "classrooms_update", "join_requests_list", "join_requests_review", "classroom_enrollments_list", "classroom_enrollments_revoke", "course_my_classrooms"})

    def test_classroom_management_schemas_expose_roster_and_own_classrooms(self):
        course = self.schema["components"]["schemas"]["Course"]
        self.assertIn("my_classrooms", course["properties"])
        self.assertTrue(course["properties"]["my_classrooms"]["readOnly"])
        roster = self.schema["components"]["schemas"]["ClassroomEnrollment"]
        self.assertIn("student", roster["properties"])
        self.assertNotIn("class_code", roster["properties"])
        path = "/api/courses/{course_id}/classrooms/{classroom_id}/enrollments/"
        operation = self.schema["paths"][path]["get"]
        self.assertIn("status", [p["name"] for p in operation["parameters"]])
        page = self.component(operation["responses"]["200"]["content"]["application/json"]["schema"])
        self.assertEqual(set(page["properties"]), {"count", "next", "previous", "results"})
        revoke = self.schema["paths"][path + "{enrollment_id}/"]["delete"]
        self.assertNotIn("requestBody", revoke)
        self.assertNotIn("content", revoke["responses"]["204"])

    def test_input_and_output_schemas_match_serializers(self):
        paths = self.schema["paths"]
        login = paths["/api/users/login/"]["post"]
        request = self.component(login["requestBody"]["content"]["application/json"]["schema"])
        self.assertEqual(set(request["properties"]), {"username", "password"})
        self.assertEqual(set(request["required"]), {"username", "password"})
        self.assertTrue(request["properties"]["password"]["writeOnly"])
        response = self.component(login["responses"]["200"]["content"]["application/json"]["schema"])
        self.assertEqual(set(response["properties"]), {"user", "access"})
        user = self.component(response["properties"]["user"])
        self.assertEqual(set(user["properties"]), {
            "id", "username", "email", "full_name", "avatar_url", "phone", "role", "status",
            "created_at", "updated_at", "last_login", "student_profile", "teacher_profile",
        })
        create = paths["/api/courses/"]["post"]
        request = self.component(create["requestBody"]["content"]["application/json"]["schema"])
        self.assertEqual(set(request["properties"]), {"title", "description"})
        patch = paths["/api/courses/{course_id}/"]["patch"]
        request = self.component(patch["requestBody"]["content"]["application/json"]["schema"])
        self.assertEqual(set(request["properties"]), {"title", "description", "status"})
        self.assertFalse(request.get("required"))

    def test_pagination_uuid_parameters_and_membership_status_codes(self):
        paths = self.schema["paths"]
        for path in ("/api/courses/", "/api/courses/{course_id}/members/"):
            operation = paths[path]["get"]
            page = self.component(operation["responses"]["200"]["content"]["application/json"]["schema"])
            self.assertEqual(set(page["properties"]), {"count", "next", "previous", "results"})
            self.assertIn("page", [parameter["name"] for parameter in operation["parameters"]])
        self.assertNotIn("post", paths["/api/courses/{course_id}/members/"])
        revoke = paths["/api/courses/{course_id}/members/{member_id}/"]["delete"]
        self.assertNotIn("content", revoke["responses"]["204"])
        for parameter in revoke["parameters"]:
            if parameter["in"] == "path":
                self.assertEqual(parameter["schema"]["format"], "uuid")
                self.assertTrue(parameter["required"])

    def test_profile_update_documents_editable_fields_and_secret_inputs(self):
        operation = self.schema["paths"]["/api/users/me/"]["patch"]
        request = self.component(operation["requestBody"]["content"]["application/json"]["schema"])
        self.assertEqual(set(request["properties"]), {
            "username", "email", "full_name", "avatar_url", "phone", "password", "password_confirm",
            "current_password", "student_profile", "teacher_profile",
        })
        self.assertFalse(request.get("required"))
        self.assertIs(request["additionalProperties"], False)
        self.assertEqual(request["minProperties"], 1)
        for field in ("password", "password_confirm", "current_password"):
            self.assertTrue(request["properties"][field]["writeOnly"])
        self.assertEqual(request["properties"]["password"]["minLength"], 8)
        for field, expected in (("student_profile", {"learning_goal"}), ("teacher_profile", {"bio", "specialization"})):
            profile = self.component(request["properties"][field])
            self.assertEqual(set(profile["properties"]), expected)
            self.assertIs(profile["additionalProperties"], False)
            self.assertEqual(profile["minProperties"], 1)
        response = self.component(operation["responses"]["200"]["content"]["application/json"]["schema"])
        self.assertEqual(set(response["properties"]), {"user", "requires_login"})

    def test_registration_requires_only_public_roles_and_documents_profile_inputs(self):
        operation = self.schema["paths"]["/api/users/register/"]["post"]
        request = self.component(operation["requestBody"]["content"]["application/json"]["schema"])
        self.assertEqual(set(request["required"]), {
            "username", "email", "password", "password_confirm", "full_name", "role",
        })
        self.assertEqual(self.component(request["properties"]["role"])["enum"], ["STUDENT", "TEACHER"])
        self.assertIs(request["additionalProperties"], False)
        self.assertTrue(request["properties"]["password"]["writeOnly"])
        self.assertTrue(request["properties"]["password_confirm"]["writeOnly"])
        self.assertTrue({"learning_goal", "bio", "specialization"} <= set(request["properties"]))
        user = self.schema["components"]["schemas"]["User"]
        self.assertNotIn("student_profile", user.get("required", []))
        self.assertNotIn("teacher_profile", user.get("required", []))

    def test_password_reset_schemas_are_public_strict_and_hide_secrets(self):
        for path, fields in (
            ("/api/users/password-reset/", {"email"}),
            ("/api/users/password-reset/confirm/", {"uid", "token", "password", "password_confirm"}),
        ):
            operation = self.schema["paths"][path]["post"]
            request = self.component(operation["requestBody"]["content"]["application/json"]["schema"])
            self.assertEqual(set(request["properties"]), fields)
            self.assertEqual(set(request["required"]), fields)
            self.assertIs(request["additionalProperties"], False)
            self.assertEqual(set(operation["responses"]), {"200", "400", "429"})
            response = self.component(operation["responses"]["200"]["content"]["application/json"]["schema"])
            if path == "/api/users/password-reset/":
                self.assertEqual(set(response["properties"]), {"detail", "reset_url"})
                self.assertNotIn("reset_url", response.get("required", []))
            else:
                self.assertEqual(set(response["properties"]), {"detail"})
            for field in fields & {"token", "password", "password_confirm"}:
                self.assertTrue(request["properties"][field]["writeOnly"])

    def test_avatar_upload_is_binary_multipart_and_strict(self):
        operation = self.schema["paths"]["/api/users/me/avatar/"]["post"]
        content = operation["requestBody"]["content"]
        self.assertIn("multipart/form-data", content)
        request = self.schema["components"]["schemas"]["AvatarUploadRequest"]
        self.assertEqual(request["properties"]["avatar"]["format"], "binary")
        self.assertEqual(request["required"], ["avatar"])
        self.assertFalse(request["additionalProperties"])

    def test_enum_overrides_stay_in_sync_with_models(self):
        expected = {
            "UserRole": User.Role.values, "UserStatus": User.Status.values,
            "CourseStatus": Course.Status.values, "CourseRole": CourseMember.Role.values,
            "MemberStatus": CourseMember.Status.values,
            "EnrollmentStatus": Enrollment.Status.values,
            "JoinRequestStatus": JoinRequest.Status.values,
        }
        for name, values in expected.items():
            self.assertEqual(self.schema["components"]["schemas"][name]["enum"], values)

    def test_write_operations_use_bearer_security_without_csrf_header(self):
        for methods in self.schema["paths"].values():
            for method, operation in methods.items():
                if method not in {"post", "patch", "delete"}:
                    continue
                self.assertNotIn("X-CSRFToken", [p["name"] for p in operation.get("parameters", [])])
        swagger = APIClient().get(reverse("swagger-ui"))
        self.assertNotContains(swagger, "X-CSRFTOKEN")
        self.assertNotContains(swagger, "/api/users/csrf/")

    def test_error_responses_include_real_shapes_and_pagination_not_found(self):
        for methods in self.schema["paths"].values():
            for operation in methods.values():
                if "400" not in operation["responses"]:
                    continue
                content = operation["responses"]["400"]["content"]["application/json"]
                alternatives = content["schema"]["additionalProperties"]["oneOf"]
                self.assertEqual({option["type"] for option in alternatives}, {"array", "string"})
                self.assertTrue(content["examples"])
        login_examples = self.schema["paths"]["/api/users/login/"]["post"]["responses"]["400"]["content"]["application/json"]["examples"]
        for example in login_examples.values():
            self.assertLessEqual(set(example["value"]), {"username", "password", "detail"})
        for path in ("/api/courses/", "/api/courses/{course_id}/members/"):
            response = self.schema["paths"][path]["get"]["responses"]["404"]
            self.assertIn("page", response["description"].lower())

    def test_strict_course_request_constraints_match_runtime(self):
        schemas = self.schema["components"]["schemas"]
        for name in ("CourseCreateRequest", "PatchedCourseUpdateRequest", "JoinByCodeRequest", "ReviewRequestRequest", "ClassroomInputRequest", "PatchedPolicyUpdateRequest"):
            self.assertIs(schemas[name]["additionalProperties"], False)
        self.assertEqual(schemas["PatchedCourseUpdateRequest"]["minProperties"], 1)

    def test_authentication_operations_have_vietnamese_summaries_and_descriptions(self):
        expected = {
            "users_register": "Đăng ký tài khoản học viên hoặc giáo viên",
            "users_login": "Đăng nhập bằng tên tài khoản và mật khẩu",
            "users_password_reset_request": "Yêu cầu liên kết đặt lại mật khẩu",
            "users_password_reset_confirm": "Đặt mật khẩu mới bằng liên kết khôi phục",
            "users_token_refresh": "Làm mới access token",
            "users_session": "Khôi phục phiên đăng nhập trên trình duyệt",
            "users_logout": "Đăng xuất và thu hồi refresh token",
            "users_me": "Xem thông tin tài khoản hiện tại",
            "users_update_me": "Cập nhật tài khoản và hồ sơ theo vai trò",
            "users_upload_avatar": "Tải ảnh đại diện từ máy lên",
        }
        operations = {
            operation["operationId"]: operation
            for methods in self.schema["paths"].values()
            for operation in methods.values()
        }
        for operation_id, summary in expected.items():
            with self.subTest(operation_id=operation_id):
                self.assertEqual(operations[operation_id]["summary"], summary)
                self.assertGreater(len(operations[operation_id]["description"]), 100)

    def test_course_operations_include_explanations_and_enrollment_auth_errors(self):
        for path, methods in self.schema["paths"].items():
            if not path.startswith("/api/courses/"):
                continue
            for method, operation in methods.items():
                with self.subTest(path=path, method=method):
                    self.assertTrue(operation["summary"])
                    self.assertGreater(len(operation["description"]), 100)
                    if "Enrollment" in operation["tags"]:
                        self.assertIn("401", operation["responses"])

    def test_course_documentation_examples_match_request_serializers(self):
        from apps.courses.api.serializers import (
            ClassroomInputSerializer, CourseCreateSerializer, CourseUpdateSerializer,
            JoinByCodeSerializer, PolicyUpdateSerializer, ReviewRequestSerializer,
        )

        cases = (
            ("/api/courses/", "post", CourseCreateSerializer),
            ("/api/courses/{course_id}/", "patch", CourseUpdateSerializer),
            ("/api/courses/{course_id}/access-policy/", "patch", PolicyUpdateSerializer),
            ("/api/courses/{course_id}/classrooms/", "post", ClassroomInputSerializer),
            ("/api/courses/{course_id}/classrooms/{classroom_id}/", "patch", ClassroomInputSerializer),
            ("/api/courses/join/", "post", JoinByCodeSerializer),
            ("/api/courses/{course_id}/join-requests/{request_id}/review/", "post", ReviewRequestSerializer),
        )
        for path, method, serializer_class in cases:
            examples = self.schema["paths"][path][method]["requestBody"]["content"]["application/json"]["examples"]
            self.assertTrue(examples)
            for example in examples.values():
                with self.subTest(path=path, example=example["value"]):
                    serializer = serializer_class(data=example["value"], partial=method == "patch")
                    self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_schema_swagger_and_health_are_public(self):
        client = APIClient()
        response = client.get(reverse("api-schema"), HTTP_ACCEPT="application/vnd.oai.openapi+json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"]["title"], "OHAYO API")
        self.assertFalse(response.json()["info"].get("description"))
        swagger = client.get(reverse("swagger-ui"))
        self.assertEqual(swagger.status_code, 200)
        self.assertContains(swagger, "SwaggerUIBundle")
        self.assertNotContains(swagger, "W2 backend: authentication, courses, and course membership.")
        self.assertNotContains(swagger, "X-CSRFTOKEN")
        self.assertContains(swagger, "drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-bundle.js")
        self.assertIsNotNone(finders.find("drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-bundle.js"))
        health = client.get(reverse("health-check"))
        self.assertEqual(health.json(), {"status": "ok", "service": "smart-lms-rag"})
