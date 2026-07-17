from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sds", "0019_teacheradmin_profile_picture"),
        ("scholarship_test", "0005_scholarshiptestattempt_test"),
    ]

    operations = [
        migrations.AddField(
            model_name="scholarshiptestattempt",
            name="portal_student",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scholarship_test_attempts",
                to="sds.student",
            ),
        ),
        migrations.AddField(
            model_name="scholarshiptestattempt",
            name="student_batch",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
    ]
