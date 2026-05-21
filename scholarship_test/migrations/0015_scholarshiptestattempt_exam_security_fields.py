from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scholarship_test', '0014_scholarshiptest_subject'),
    ]

    operations = [
        migrations.AddField(
            model_name='scholarshiptestattempt',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='scholarshiptestattempt',
            name='submitted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='scholarshiptestattempt',
            name='violation_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='scholarshiptestattempt',
            name='security_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('active', 'Active'),
                    ('warning', 'Warning'),
                    ('submitted', 'Submitted'),
                    ('locked', 'Locked'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
    ]
