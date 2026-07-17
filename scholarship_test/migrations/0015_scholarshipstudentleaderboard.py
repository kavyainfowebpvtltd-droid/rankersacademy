from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sds", "0023_alter_teacheradmin_role"),
        ("scholarship_test", "0014_scholarshiptest_subject"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScholarshipStudentLeaderboard",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("student_batch", models.CharField(blank=True, default="", max_length=50)),
                ("phy_marks", models.IntegerField(default=0)),
                ("chm_marks", models.IntegerField(default=0)),
                ("bio_marks", models.IntegerField(default=0)),
                ("math_marks", models.IntegerField(default=0)),
                ("total_score", models.IntegerField(default=0)),
                ("phy_tests_count", models.IntegerField(default=0)),
                ("chm_tests_count", models.IntegerField(default=0)),
                ("bio_tests_count", models.IntegerField(default=0)),
                ("math_tests_count", models.IntegerField(default=0)),
                ("batch_rank", models.IntegerField(blank=True, null=True)),
                ("institute_rank", models.IntegerField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "portal_student",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="scholarship_leaderboard", to="sds.student"),
                ),
            ],
            options={
                "ordering": ["-total_score", "portal_student_id"],
            },
        ),
    ]
