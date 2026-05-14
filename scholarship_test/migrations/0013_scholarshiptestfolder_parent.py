from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("scholarship_test", "0012_scholarshiptestfaculty_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="scholarshiptestfolder",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="children",
                to="scholarship_test.scholarshiptestfolder",
            ),
        ),
    ]

