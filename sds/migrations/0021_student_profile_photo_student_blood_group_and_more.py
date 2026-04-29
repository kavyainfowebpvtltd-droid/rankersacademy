from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sds", "0020_student_username"),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="blood_group",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
        migrations.AddField(
            model_name="student",
            name="emergency_contact",
            field=models.CharField(blank=True, default="", max_length=15),
        ),
        migrations.AddField(
            model_name="student",
            name="emergency_contact_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="student",
            name="father_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="student",
            name="profile_photo",
            field=models.ImageField(blank=True, null=True, upload_to="student_profiles/"),
        ),
        migrations.AddField(
            model_name="student",
            name="stream",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
