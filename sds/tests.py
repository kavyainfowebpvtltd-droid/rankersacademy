from django.contrib.auth.models import User
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
