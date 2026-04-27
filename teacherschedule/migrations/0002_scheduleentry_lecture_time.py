from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("teacherschedule", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduleentry",
            name="lecture_time",
            field=models.TimeField(blank=True, null=True),
        ),
    ]
