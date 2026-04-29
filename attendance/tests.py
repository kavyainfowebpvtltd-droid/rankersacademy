from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from attendance.models import Attendance
from attendance.services import process_absent_attendance, record_kiosk_scan
from sds.models import Student


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
