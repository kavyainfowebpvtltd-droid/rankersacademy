import csv
import re
from collections import Counter

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from sds.models import Student


def _normalize_phone(value):
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits


class Command(BaseCommand):
    help = "Audit student login credentials without changing any data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="Optional CSV path for the audit report.",
        )

    def handle(self, *args, **options):
        students = list(Student.objects.select_related("user").order_by("id"))
        normalized_contacts = [_normalize_phone(student.contact) for student in students]
        duplicate_contacts = {
            contact
            for contact, count in Counter(normalized_contacts).items()
            if contact and count > 1
        }

        user_email_counts = Counter(
            (email or "").strip().lower()
            for email in User.objects.values_list("email", flat=True)
            if (email or "").strip()
        )

        rows = []
        for student in students:
            user = student.user
            issues = []

            student_username = (student.username or "").strip()
            user_username = (user.username or "").strip()
            student_email = (student.email or "").strip()
            user_email = (user.email or "").strip()
            normalized_contact = _normalize_phone(student.contact)

            if not student_username:
                issues.append("blank_student_username")
            if not user_username:
                issues.append("blank_auth_username")
            if student_username and user_username and student_username != user_username:
                issues.append("username_mismatch")
            if student_email.lower() != user_email.lower():
                issues.append("email_mismatch")
            if not user.is_active:
                issues.append("inactive_user")
            if not user.has_usable_password():
                issues.append("unusable_password")
            if normalized_contact in duplicate_contacts:
                issues.append("duplicate_contact")
            if user_email and user_email_counts[user_email.lower()] > 1:
                issues.append("duplicate_auth_email")

            if issues:
                rows.append(
                    {
                        "student_id": student.id,
                        "user_id": user.id,
                        "student_name": student.student_name,
                        "issues": ",".join(issues),
                        "student_username": student_username,
                        "auth_username": user_username,
                        "student_email": student_email,
                        "auth_email": user_email,
                        "contact": student.contact,
                        "is_active": user.is_active,
                        "has_usable_password": user.has_usable_password(),
                    }
                )

        output_path = options.get("output")
        if output_path:
            fieldnames = [
                "student_id",
                "user_id",
                "student_name",
                "issues",
                "student_username",
                "auth_username",
                "student_email",
                "auth_email",
                "contact",
                "is_active",
                "has_usable_password",
            ]
            with open(output_path, "w", newline="", encoding="utf-8") as report_file:
                writer = csv.DictWriter(report_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(self.style.SUCCESS(f"Wrote {len(rows)} issue rows to {output_path}"))
        else:
            self.stdout.write(f"Students audited: {len(students)}")
            self.stdout.write(f"Students with credential issues: {len(rows)}")
            for row in rows[:50]:
                self.stdout.write(
                    f"{row['student_id']}: {row['student_name']} [{row['issues']}]"
                )
            if len(rows) > 50:
                self.stdout.write(f"... {len(rows) - 50} more rows. Use --output for full CSV.")
