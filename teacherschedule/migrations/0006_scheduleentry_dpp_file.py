from django.db import migrations, models
import teacherschedule.models


class Migration(migrations.Migration):

    dependencies = [
        ("teacherschedule", "0005_alter_uploadedschedule_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduleentry",
            name="dpp_file",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=teacherschedule.models.dpp_pdf_upload_path,
            ),
        ),
    ]
