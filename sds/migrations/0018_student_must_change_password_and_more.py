from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sds", "0017_question_question_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="must_change_password",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="teacheradmin",
            name="must_change_password",
            field=models.BooleanField(default=False),
        ),
    ]
