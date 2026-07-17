from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scholarship_test", "0013_scholarshiptestfolder_parent"),
    ]

    operations = [
        migrations.AddField(
            model_name="scholarshiptest",
            name="subject",
            field=models.CharField(blank=True, default="Physics", max_length=50),
        ),
    ]

