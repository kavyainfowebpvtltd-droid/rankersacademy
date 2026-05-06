from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scholarship_test", "0008_scholarshiptestattempt_progress_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="scholarshiptest",
            name="scheduled_start_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
