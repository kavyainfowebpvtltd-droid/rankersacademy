from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0003_staffattendance"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffattendance",
            name="daily_tasks",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="staffattendance",
            name="task_status",
            field=models.TextField(blank=True, default=""),
        ),
    ]
