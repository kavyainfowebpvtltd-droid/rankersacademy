from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scholarship_test', '0007_rankpredictorlead'),
    ]

    operations = [
        migrations.AddField(
            model_name='scholarshiptestattempt',
            name='progress_state',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
