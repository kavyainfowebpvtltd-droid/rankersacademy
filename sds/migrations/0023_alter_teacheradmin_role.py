from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sds", "0022_teacheradmin_blood_group"),
    ]

    operations = [
        migrations.AlterField(
            model_name="teacheradmin",
            name="role",
            field=models.CharField(max_length=80),
        ),
    ]
