from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sds", "0021_student_profile_photo_student_blood_group_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacheradmin",
            name="blood_group",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
    ]
