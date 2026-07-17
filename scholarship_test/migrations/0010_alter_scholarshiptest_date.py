from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("scholarship_test", "0009_scholarshiptest_scheduled_start_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="scholarshiptest",
            name="date",
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
    ]
