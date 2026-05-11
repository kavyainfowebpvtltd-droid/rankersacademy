from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from attendance.models import Attendance, StaffAttendance
from attendance.services import process_absent_attendance, record_kiosk_scan, record_staff_scan
from sds.models import Student, TeacherAdmin


class AttendanceKioskServiceTests(TestCase):
    def setUp(self):
        self.student_user = User.objects.create_user(username="S0101", password="testpass123")
        self.student = Student.objects.create(
            user=self.student_user,
            student_name="Nayan Dakhole",
            username="S0101",
            contact="7410545815",
            email="nayan@example.com",
            school="Rankers Academy",
            board="CBSE",
            grade="10",
            batch="Star 01",
            gender="Male",
        )

    @patch("attendance.services.send_attendance_sms", return_value=True)
    def test_star_batch_before_cutoff_marks_present(self, mocked_sms):
        result = record_kiosk_scan(str(self.student.id), scanned_at="2026-04-24T03:10:00Z")

        attendance = Attendance.objects.get(student=self.student, date="2026-04-24")
        self.assertEqual(attendance.status, "Present")
        self.assertEqual(result["action"], "checkin")
        mocked_sms.assert_called_once()

    @patch("attendance.services.send_attendance_sms", return_value=True)
    def test_alpha_batch_after_cutoff_marks_late(self, mocked_sms):
        self.student.batch = "Alpha"
        self.student.save(update_fields=["batch"])

        result = record_kiosk_scan(str(self.student.id), scanned_at="2026-04-24T03:00:00Z")

        attendance = Attendance.objects.get(student=self.student, date="2026-04-24")
        self.assertEqual(attendance.status, "Late")
        self.assertEqual(result["action"], "late_entry")
        mocked_sms.assert_called_once()

    @patch("attendance.services.send_attendance_sms", return_value=True)
    def test_checkout_requires_five_pm_or_later(self, mocked_sms):
        record_kiosk_scan(str(self.student.id), scanned_at="2026-04-24T02:30:00Z")

        early_result = record_kiosk_scan(str(self.student.id), scanned_at="2026-04-24T10:00:00Z")
        self.assertEqual(early_result["action"], "already_checked_in")

        late_result = record_kiosk_scan(str(self.student.id), scanned_at="2026-04-24T11:45:00Z")
        attendance = Attendance.objects.get(student=self.student, date="2026-04-24")

        self.assertEqual(late_result["action"], "checkout")
        self.assertIsNotNone(attendance.check_out)
        self.assertEqual(mocked_sms.call_count, 2)

    @patch("attendance.services.send_attendance_sms", return_value=True)
    def test_qr_with_comma_separated_labeled_fields_resolves_student(self, mocked_sms):
        qr_value = (
            "Student Name: Nayan Dakhole, "
            "Username: S0101, "
            "Contact Number: 7410545815, "
            "Batch: Star 01, "
            "Board: JEE"
        )

        result = record_kiosk_scan(qr_value, scanned_at="2026-04-24T03:10:00Z")

        attendance = Attendance.objects.get(student=self.student, date="2026-04-24")
        self.assertEqual(attendance.status, "Present")
        self.assertEqual(result["student_id"], self.student.id)
        mocked_sms.assert_called_once()

    @patch("attendance.services.send_attendance_sms", return_value=True)
    def test_qr_with_multiline_label_format_returns_student_photo(self, mocked_sms):
        self.student.profile_photo = "student_profiles/nayan.jpg"
        self.student.save(update_fields=["profile_photo"])

        qr_value = (
            "Name : Nayan Dakhole\n"
            "Username : S0101\n"
            "Stream : NEET\n"
            "Batch : Star 01\n"
            "Contact No : 7410545815\n"
            "Email ID : nayan@example.com"
        )

        result = record_kiosk_scan(qr_value, scanned_at="2026-04-24T03:10:00Z")

        self.assertEqual(result["student_id"], self.student.id)
        self.assertEqual(result["studentName"], self.student.student_name)
        self.assertEqual(result["studentBatch"], self.student.batch)
        self.assertEqual(result["photoUrl"], "/media/student_profiles/nayan.jpg")
        mocked_sms.assert_called_once()


class AttendanceAbsentProcessingTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="A0101", password="testpass123")
        self.student = Student.objects.create(
            user=user,
            student_name="Absent Student",
            contact="9876543210",
            email="absent@example.com",
            school="Rankers Academy",
            board="CBSE",
            grade="11",
            batch="Star 02",
            gender="Female",
        )

    @patch("attendance.services.send_attendance_sms", return_value=True)
    def test_process_absent_attendance_creates_record(self, mocked_sms):
        target_date = timezone.now().date() - timedelta(days=1)
        while target_date.weekday() >= 5:
            target_date -= timedelta(days=1)

        created_count = process_absent_attendance(target_date=target_date, allow_today=False)

        attendance = Attendance.objects.get(student=self.student, date=target_date)
        self.assertEqual(created_count, 1)
        self.assertEqual(attendance.status, "Absent")
        mocked_sms.assert_called_once()


class StaffAttendanceServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="admin.staff", password="testpass123")
        self.staff = TeacherAdmin.objects.create(
            user=self.user,
            name="Asha Kulkarni",
            username="admin.staff",
            email="asha@example.com",
            contact="9123456780",
            gender="Female",
            role="Admin",
        )

    def test_staff_qr_scan_marks_present(self):
        result = record_staff_scan(
            "Name: Asha Kulkarni, Username: admin.staff, Contact Number: 9123456780",
            scanned_at="2026-04-24T03:10:00Z",
        )

        attendance = StaffAttendance.objects.get(staff=self.staff, date="2026-04-24")
        self.assertEqual(attendance.status, "Present")
        self.assertEqual(result["action"], "checkin")
        self.assertEqual(result["staff_id"], self.staff.id)

    def test_second_staff_scan_after_checkout_cutoff_marks_checkout(self):
        record_staff_scan(str(self.staff.id), scanned_at="2026-04-24T03:10:00Z")
        result = record_staff_scan(str(self.staff.id), scanned_at="2026-04-24T11:45:00Z")

        attendance = StaffAttendance.objects.get(staff=self.staff, date="2026-04-24")
        self.assertEqual(result["action"], "checkout")
        self.assertIsNotNone(attendance.check_out)


class StaffAttendancePageTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(username="admin.user", password="testpass123")
        self.admin_staff = TeacherAdmin.objects.create(
            user=self.admin_user,
            name="Admin User",
            username="admin.user",
            email="admin.user@example.com",
            contact="9000000001",
            gender="Female",
            role="Admin",
        )
        self.teacher_user = User.objects.create_user(username="teacher.one", password="testpass123")
        self.teacher_staff = TeacherAdmin.objects.create(
            user=self.teacher_user,
            name="Teacher One",
            username="teacher.one",
            email="teacher.one@example.com",
            contact="9000000002",
            gender="Male",
            role="Teacher",
        )
        self.counselor_user = User.objects.create_user(username="counselor.one", password="testpass123")
        self.counselor_staff = TeacherAdmin.objects.create(
            user=self.counselor_user,
            name="Counselor One",
            username="counselor.one",
            email="counselor.one@example.com",
            contact="9000000003",
            gender="Female",
            role="Counselor",
        )

    def test_staff_attendance_page_lists_each_staff_member_once(self):
        StaffAttendance.objects.create(
            staff=self.teacher_staff,
            date="2026-05-01",
            status="Present",
        )
        StaffAttendance.objects.create(
            staff=self.teacher_staff,
            date="2026-05-02",
            status="Late",
        )
        StaffAttendance.objects.create(
            staff=self.admin_staff,
            date="2026-05-01",
            status="Absent",
        )

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("staff_attendance"), {"month": "2026-05"})

        self.assertEqual(response.status_code, 200)

        rows = response.context["attendance_rows"]
        row_by_staff_id = {row["staff"].id: row for row in rows}

        self.assertEqual(len(rows), 3)
        self.assertEqual(set(row_by_staff_id.keys()), {self.admin_staff.id, self.teacher_staff.id, self.counselor_staff.id})
        self.assertEqual(row_by_staff_id[self.teacher_staff.id]["present_days"], 1)
        self.assertEqual(row_by_staff_id[self.teacher_staff.id]["late_days"], 1)
        self.assertEqual(row_by_staff_id[self.teacher_staff.id]["total_days"], 2)
        self.assertEqual(row_by_staff_id[self.counselor_staff.id]["total_days"], 0)
