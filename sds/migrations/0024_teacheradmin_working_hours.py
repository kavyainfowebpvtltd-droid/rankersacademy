from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sds", "0023_alter_teacheradmin_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacheradmin",
            name="working_hours",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
