from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scholarship_test", "0012_scholarshiptestfaculty_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="scholarshiptest",
            name="original_word_file",
            field=models.FileField(blank=True, null=True, upload_to="scholarship_test_files/"),
        ),
    ]
