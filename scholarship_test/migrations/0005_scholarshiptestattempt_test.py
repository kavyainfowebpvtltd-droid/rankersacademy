from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('scholarship_test', '0004_scholarshiptestimage'),
    ]

    operations = [
        migrations.AddField(
            model_name='scholarshiptestattempt',
            name='test',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='attempts',
                to='scholarship_test.scholarshiptest',
            ),
        ),
    ]
