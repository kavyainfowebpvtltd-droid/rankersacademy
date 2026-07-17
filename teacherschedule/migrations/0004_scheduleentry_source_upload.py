from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("teacherschedule", "0003_uploadedschedule_teacher"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduleentry",
            name="source_upload",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="schedule_entries",
                to="teacherschedule.uploadedschedule",
            ),
        ),
    ]
