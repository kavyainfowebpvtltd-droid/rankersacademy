from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scholarship_test", "0010_alter_scholarshiptest_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="scholarshiptest",
            name="batch",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="scholarshiptest",
            name="stream",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
    ]
