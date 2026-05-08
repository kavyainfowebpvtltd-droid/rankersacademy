from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sds", "0023_alter_teacheradmin_role"),
        ("scholarship_test", "0012_scholarshiptestfaculty_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScholarshipTestParentCommunication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message_type", models.CharField(choices=[("post-test", "Post-Test"), ("absence", "Absence")], max_length=20)),
                ("subject", models.CharField(blank=True, default="", max_length=20)),
                ("tone", models.CharField(blank=True, default="", max_length=30)),
                ("parent_phone", models.CharField(blank=True, default="", max_length=20)),
                ("message_body", models.TextField(blank=True, default="")),
                ("sent_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("portal_student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scholarship_test_parent_communications", to="sds.student")),
                ("sent_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="scholarship_test_parent_communications_sent", to=settings.AUTH_USER_MODEL)),
                ("test", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="parent_communications", to="scholarship_test.scholarshiptest")),
            ],
            options={
                "ordering": ["-sent_at", "-id"],
                "unique_together": {("test", "portal_student", "message_type", "subject")},
            },
        ),
    ]
