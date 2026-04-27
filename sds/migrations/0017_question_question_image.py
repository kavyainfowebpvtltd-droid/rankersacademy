from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sds", "0016_student_report_email_error_student_report_email_sent_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="question_image",
            field=models.ImageField(blank=True, null=True, upload_to="mcq_images/"),
        ),
    ]
