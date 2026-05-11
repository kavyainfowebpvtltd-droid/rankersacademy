import json

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

from sds.models import Student, TeacherAdmin
from sds.password_policy import DEFAULT_ONE_TIME_PASSWORD


@override_settings(ROOT_URLCONF="sds.urls")
class AddUserStudentFieldSelectionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        self.client.force_login(self.admin)

    def test_add_student_prefers_student_grade_board_batch_when_duplicate_fields_exist(self):
        response = self.client.post(
            reverse("add_user"),
            {
                "user_type": "student",
                "name": "Aarav",
                "username": "aarav01",
                "email": "aarav@example.com",
                "contact": "9876543210",
                "password": "strong-pass-123",
                "gender": "Male",
                "school": "Rankers School",
                "board": ["CBSE", ""],
                "grade": ["10th", ""],
                "batch": ["B2", ""],
            },
        )

        self.assertRedirects(response, reverse("user-management"))

        student = Student.objects.get(email="aarav@example.com")
        self.assertEqual(student.board, "CBSE")
        self.assertEqual(student.grade, "10th")
        self.assertEqual(student.batch, "B2")
        self.assertEqual(student.username, student.user.username)
        self.assertTrue(student.must_change_password)
        self.assertTrue(student.user.check_password(DEFAULT_ONE_TIME_PASSWORD))


@override_settings(ROOT_URLCONF="sds.urls")
class ForcedPasswordChangeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="teacher01",
            email="teacher01@example.com",
            password=DEFAULT_ONE_TIME_PASSWORD,
        )
        self.teacher = TeacherAdmin.objects.create(
            user=self.user,
            name="Teacher One",
            username="teacher01",
            email="teacher01@example.com",
            contact="9876543211",
            gender="Male",
            role="Teacher",
            must_change_password=True,
        )

    def test_first_login_redirects_to_force_password_change(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "teacher01",
                "password": DEFAULT_ONE_TIME_PASSWORD,
                "role": "Teacher/Admin",
            },
        )

        self.assertRedirects(response, reverse("force_password_change"))

    def test_successful_forced_password_change_clears_flag(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("force_password_change"),
            {
                "old_password": DEFAULT_ONE_TIME_PASSWORD,
                "new_password1": "StrongPass@2026",
                "new_password2": "StrongPass@2026",
            },
        )

        self.assertRedirects(response, reverse("admin-dashboard"))
        self.teacher.refresh_from_db()
        self.user.refresh_from_db()
        self.assertFalse(self.teacher.must_change_password)
        self.assertTrue(self.user.check_password("StrongPass@2026"))


@override_settings(ROOT_URLCONF="sds.urls", MAX_LOGIN_ATTEMPTS=5)
class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

        self.first_user = User.objects.create_user(
            username="student01",
            email="student01@example.com",
            password="StudentPass@2026",
        )
        self.second_user = User.objects.create_user(
            username="student02",
            email="student02@example.com",
            password="AnotherPass@2026",
        )

        Student.objects.create(
            user=self.first_user,
            student_name="Student One",
            username="student01",
            contact="9876543214",
            email="student01@example.com",
            school="Rankers School",
            board="CBSE",
            grade="10th",
            batch="B1",
            gender="Male",
        )
        Student.objects.create(
            user=self.second_user,
            student_name="Student Two",
            username="student02",
            contact="9876543215",
            email="student02@example.com",
            school="Rankers School",
            board="CBSE",
            grade="10th",
            batch="B1",
            gender="Female",
        )

    def tearDown(self):
        cache.clear()

    def test_failed_attempts_do_not_lock_other_users_on_same_ip(self):
        shared_ip = "203.0.113.10"

        for _ in range(5):
            response = self.client.post(
                reverse("login"),
                {
                    "username": "unknown-user",
                    "password": "wrong-password",
                    "role": "Student",
                },
                REMOTE_ADDR=shared_ip,
            )
            self.assertRedirects(response, reverse("login"))

        response = self.client.post(
            reverse("login"),
            {
                "username": "student02",
                "password": "AnotherPass@2026",
                "role": "Student",
            },
            REMOTE_ADDR=shared_ip,
        )

        self.assertRedirects(response, reverse("student-dashboard"))

    def test_account_lock_still_applies_after_repeated_failures(self):
        for _ in range(5):
            response = self.client.post(
                reverse("login"),
                {
                    "username": "student01",
                    "password": "wrong-password",
                    "role": "Student",
                },
                REMOTE_ADDR="198.51.100.25",
            )
            self.assertRedirects(response, reverse("login"))

        response = self.client.post(
            reverse("login"),
            {
                "username": "student01",
                "password": "StudentPass@2026",
                "role": "Student",
            },
            REMOTE_ADDR="198.51.100.25",
            follow=True,
        )

        self.assertEqual(response.resolver_match.view_name, "login")
        self.assertContains(
            response,
            "Account temporarily locked due to too many failed attempts.",
        )


@override_settings(ROOT_URLCONF="sds.urls")
class AdminDashboardSearchTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        self.client.force_login(self.admin)

        self.student_user = User.objects.create_user(
            username="RK-2026_01",
            email="rk-2026_01@example.com",
            password="studentpass123",
        )
        self.student = Student.objects.create(
            user=self.student_user,
            student_name="Rohit Kumar",
            username="RK-2026_01",
            contact="9876543212",
            email="rk-2026_01@example.com",
            school="Rankers School",
            board="CBSE",
            grade="10th",
            batch="B1",
            gender="Male",
        )

        self.other_user = User.objects.create_user(
            username="AB20262802",
            email="aanya@example.com",
            password="studentpass123",
        )
        self.other_student = Student.objects.create(
            user=self.other_user,
            student_name="Aanya Sharma",
            username="AB20262802",
            contact="9876543213",
            email="aanya@example.com",
            school="Rankers School",
            board="CBSE",
            grade="10th",
            batch="B1",
            gender="Female",
        )

    def test_admin_dashboard_search_matches_roll_number_format(self):
        response = self.client.get(
            reverse("admin-dashboard"),
            {"search": "RK-2026_01"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rohit Kumar")
        self.assertNotContains(response, "Aanya Sharma")
        self.assertEqual(response.context["active_search_query"], "RK-2026_01")

    def test_admin_dashboard_search_matches_email(self):
        response = self.client.get(
            reverse("admin-dashboard"),
            {"search": "rk-2026_01@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rohit Kumar")
        self.assertNotContains(response, "Aanya Sharma")

    def test_admin_dashboard_ajax_search_returns_only_table_section(self):
        response = self.client.get(
            reverse("admin-dashboard"),
            {"search": "RK-2026_01"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="adminDashboardTableSection"')
        self.assertContains(response, "Rohit Kumar")
        self.assertNotContains(response, 'id="adminDashboardSearchForm"')


@override_settings(ROOT_URLCONF="sds.urls")
class StudentPortalFeatureVisibilityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="studentportal01",
            email="studentportal01@example.com",
            password="StudentPass@2026",
        )
        self.student = Student.objects.create(
            user=self.user,
            student_name="Portal Student",
            username="studentportal01",
            contact="9876543220",
            email="studentportal01@example.com",
            school="Rankers School",
            board="CBSE",
            grade="10th",
            batch="B1",
            gender="Male",
        )
        self.client.force_login(self.user)

    def test_hidden_features_are_not_rendered_in_student_navigation(self):
        response = self.client.get(reverse("student-dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Subject Analysis")
        self.assertNotContains(response, "Gap Analysis")
        self.assertNotContains(response, "Reports")
        self.assertNotContains(response, "Download Imp. Questions and Solutions")

    def test_hidden_feature_pages_redirect_students_to_dashboard(self):
        urls = [
            reverse("subject_analysis"),
            reverse("gap_analysis"),
            reverse("reports"),
            reverse("study_material"),
            reverse("ssc_state"),
        ]

        for url in urls:
            response = self.client.get(url)
            self.assertRedirects(response, reverse("student-dashboard"))

    def test_hidden_report_endpoints_are_blocked_for_students(self):
        pdf_response = self.client.get(reverse("pdf-report", args=[self.student.id]))
        self.assertRedirects(pdf_response, reverse("student-dashboard"))

        print_response = self.client.get(reverse("print-report", args=[self.student.id]))
        self.assertRedirects(print_response, reverse("student-dashboard"))

        email_response = self.client.post(
            reverse("send-report-email-api"),
            data=json.dumps({"student_id": self.student.id}),
            content_type="application/json",
        )
        self.assertEqual(email_response.status_code, 403)
        self.assertJSONEqual(
            email_response.content.decode("utf-8"),
            {
                "success": False,
                "msg": "This section is currently hidden in the student portal.",
            },
        )
