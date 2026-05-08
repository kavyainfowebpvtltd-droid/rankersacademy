from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sds", "0023_alter_teacheradmin_role"),
        ("scholarship_test", "0011_scholarshiptest_batch_scholarshiptest_stream"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScholarshipTestFacultyAttendanceSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject", models.CharField(max_length=20)),
                ("finalized", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "test",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="faculty_attendance_sessions",
                        to="scholarship_test.scholarshiptest",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scholarship_test_attendance_sessions_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["test", "subject"],
                "unique_together": {("test", "subject")},
            },
        ),
        migrations.CreateModel(
            name="ScholarshipTestFacultyAttendance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject", models.CharField(max_length=20)),
                ("status", models.CharField(choices=[("present", "Present"), ("late", "Late"), ("absent", "Absent")], max_length=10)),
                ("marked_at", models.DateTimeField(auto_now=True)),
                (
                    "marked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scholarship_test_faculty_attendance_marked",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "portal_student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scholarship_test_faculty_attendance_records",
                        to="sds.student",
                    ),
                ),
                (
                    "test",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="faculty_attendance_records",
                        to="scholarship_test.scholarshiptest",
                    ),
                ),
            ],
            options={
                "ordering": ["test", "subject", "portal_student"],
                "unique_together": {("test", "portal_student", "subject")},
            },
        ),
        migrations.CreateModel(
            name="ScholarshipTestFacultyNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject", models.CharField(max_length=20)),
                ("note_text", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scholarship_test_faculty_notes_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "portal_student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scholarship_test_faculty_notes",
                        to="sds.student",
                    ),
                ),
                (
                    "test",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="faculty_notes",
                        to="scholarship_test.scholarshiptest",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
