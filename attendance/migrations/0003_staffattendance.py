from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0002_attendance_absent_sms_sent_at_attendance_check_in_and_more"),
        ("sds", "0021_student_profile_photo_student_blood_group_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffAttendance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("status", models.CharField(choices=[("Present", "Present"), ("Late", "Late"), ("Absent", "Absent")], max_length=10)),
                ("check_in", models.TimeField(blank=True, null=True)),
                ("check_out", models.TimeField(blank=True, null=True)),
                ("raw_scan_value", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "staff",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_records",
                        to="sds.teacheradmin",
                    ),
                ),
            ],
            options={
                "ordering": ("-date", "-check_in", "staff__name"),
                "unique_together": {("staff", "date")},
            },
        ),
    ]
