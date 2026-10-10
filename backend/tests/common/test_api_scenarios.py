import json
import os
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from apps.courses.models import Course, CourseMember
from apps.users.models import User
from common.testing import authenticate_client


PASSWORD = "Scenario-Test-Only-839!"


class W2APIScenarioTests(TestCase):
    """JWT integration scenarios against the isolated Django test database."""

    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for name, role, status in (
            ("teacher", User.Role.TEACHER, User.Status.ACTIVE),
            ("other_teacher", User.Role.TEACHER, User.Status.ACTIVE),
            ("student", User.Role.STUDENT, User.Status.ACTIVE),
            ("admin", User.Role.ADMIN, User.Status.ACTIVE),
            ("blocked", User.Role.STUDENT, User.Status.BLOCKED),
        ):
            cls.users[name] = User.objects.create_user(
                name, password=PASSWORD, role=role, status=status,
            )

    def setUp(self):
        self.rows = []
        self.request_count = 0
        self.teacher = APIClient()
        self.student = APIClient()
        self.anonymous = APIClient()
        self.active_row = None

    def tearDown(self):
        destination = os.getenv("W2_SCENARIO_REPORT")
        if destination:
            report = {
                "database_engine": settings.DATABASES["default"]["ENGINE"],
                "database_name": str(settings.DATABASES["default"]["NAME"]),
                "request_count": self.request_count,
                "scenario_count": len(self.rows),
                "passed": sum(row["passed"] for row in self.rows),
                "scenarios": self.rows,
            }
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
        super().tearDown()

    @contextmanager
    def case(self, name, meaning, expected):
        row = {
            "stt": len(self.rows) + 1, "test_case": name, "meaning": meaning,
            "expected": expected, "actual": "", "requests": [], "passed": False,
        }
        self.rows.append(row)
        self.active_row = row
        try:
            yield row
        except Exception as error:
            row["actual"] = str(error)
            raise
        else:
            row["passed"] = True
            print(f"W2 scenario {row['stt']:02}: PASS | {name} | {row['actual']}")
        finally:
            self.active_row = None

    def request(self, client, method, url, expected, data=None, **headers):
        self.request_count += 1
        kwargs = {"format": "json", **headers} if data is not None else headers
        response = getattr(client, method)(url, data, **kwargs) if data is not None else getattr(client, method)(url, **kwargs)
        if self.active_row is not None:
            entry = {"method": method.upper(), "url": url, "status": response.status_code}
            if response.status_code >= 400 and "application/json" in response.get("Content-Type", ""):
                entry["error"] = response.json()
            self.active_row["requests"].append(entry)
        self.assertEqual(response.status_code, expected, f"{method.upper()} {url}: {response.content!r}")
        return response

    def login(self, client, name, expected=200, password=PASSWORD):
        response = self.request(client, "post", "/api/users/login/", expected, {"username": name, "password": password})
        if expected == 200:
            authenticate_client(client, response.json()["access"] and self.users[name])
        return response

    def write(self, client, method, url, expected, data=None):
        return self.request(client, method, url, expected, data)

    def test_w2_documented_jwt_scenarios(self):
        with self.case("Health", "Public service health endpoint", "200 with service status") as row:
            self.assertEqual(self.request(self.anonymous, "get", "/api/health/", 200).json()["status"], "ok")
            row["actual"] = "200; status=ok"

        with self.case("Teacher login + bearer profile", "JWT login returns access and safe user fields", "200 login/me; HttpOnly refresh cookie") as row:
            login = self.login(self.teacher, "teacher")
            self.assertEqual(set(login.json()), {"user", "access"})
            self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, login.cookies)
            me = self.request(self.teacher, "get", "/api/users/me/", 200)
            self.assertEqual(me.json()["user"], login.json()["user"])
            row["actual"] = "200/200; bearer access; refresh cookie; safe user fields and profiles"

        with self.case("Create and publish course", "Teacher JWT authorizes course lifecycle", "201 DRAFT then 200 PUBLISHED") as row:
            created = self.write(self.teacher, "post", "/api/courses/", 201, {"title": "W2 JWT course", "description": "Original"}).json()
            course_id = created["id"]
            self.assertEqual(created["status"], "DRAFT")
            detail = f"/api/courses/{course_id}/"
            published = self.write(self.teacher, "patch", detail, 200, {"status": "PUBLISHED"}).json()
            self.assertIsNotNone(published["published_at"])
            row["actual"] = "201 DRAFT owner; 200 PUBLISHED with timestamp"

        members = f"/api/courses/{course_id}/members/"
        with self.case("Join and student read", "Class code enables free PUBLISHED course visibility", "201 join; student list/detail 200") as row:
            self.write(self.teacher, "post", f"/api/courses/{course_id}/classrooms/", 201, {"name":"Scenario class"})
            code = self.request(self.teacher, "get", f"/api/courses/{course_id}/classrooms/", 200).json()["results"][0]["class_code"]
            self.login(self.student, "student")
            self.write(self.student, "post", "/api/courses/join/", 201, {"class_code": code})
            self.assertEqual(self.request(self.student, "get", "/api/courses/", 200).json()["count"], 1)
            self.request(self.student, "get", detail, 200)
            row["actual"] = "201 join; 200 list/detail for student"

        with self.case("Student management denial", "Read permission does not grant course mutation", "403 on course and member writes") as row:
            self.write(self.student, "post", "/api/courses/", 403, {"title": "Denied"})
            self.write(self.student, "patch", detail, 403, {"title": "Denied"})
            self.write(self.student, "patch", f"/api/courses/{course_id}/access-policy/", 403, {"require_approval": False})
            row["actual"] = "403 x3 with valid student bearer token"

        with self.case("Missing bearer token", "Protected APIs reject anonymous requests", "401 for profile and business API") as row:
            self.request(self.anonymous, "get", "/api/users/me/", 401)
            self.write(self.anonymous, "post", "/api/courses/", 401, {"title": "Denied"})
            self.request(self.anonymous, "get", detail, 401)
            row["actual"] = "401 x3"

        with self.case("JWT refresh rotation", "Refresh cookie creates new access and revokes prior refresh", "200 new access; rotated cookie; blacklist entry") as row:
            before = self.teacher.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
            refreshed = self.request(self.teacher, "post", "/api/users/token/refresh/", 200)
            self.assertTrue(refreshed.json()["access"])
            self.assertNotEqual(before, self.teacher.cookies[settings.JWT_REFRESH_COOKIE_NAME].value)
            self.assertTrue(BlacklistedToken.objects.exists())
            row["actual"] = "200 access; refresh rotated and previous JTI blacklisted"

        with self.case("Logout revocation", "Logout revokes current refresh token and clears cookie", "204 logout; refresh denied 401") as row:
            self.write(self.teacher, "post", "/api/users/logout/", 204)
            self.request(self.teacher, "post", "/api/users/token/refresh/", 401)
            row["actual"] = "204; refresh cookie cleared; refresh endpoint 401"

        with self.case("Invalid login", "Avoid account enumeration", "401 generic response") as row:
            errors = [self.login(self.anonymous, username, 401, password).json() for username, password in (("teacher", "wrong"), ("unknown", PASSWORD), ("blocked", PASSWORD))]
            self.assertTrue(all(error == errors[0] for error in errors))
            row["actual"] = "401 x3; identical generic detail"

        with self.case("CSRF endpoint removed", "JWT API has no CSRF bootstrap path", "404") as row:
            self.request(self.anonymous, "get", "/api/users/csrf/", 404)
            row["actual"] = "404; no CSRF API remains"
