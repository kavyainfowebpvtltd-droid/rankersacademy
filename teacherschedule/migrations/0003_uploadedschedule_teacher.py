from django.db import migrations, models
import django.db.models.deletion


def add_teacher_column_if_missing(apps, schema_editor):
    table_name = "teacherschedule_uploadedschedule"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE 'teacher_id'")
        column_exists = cursor.fetchone() is not None

    if not column_exists:
        schema_editor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN teacher_id bigint NULL"
        )


def drop_teacher_column_if_present(apps, schema_editor):
    table_name = "teacherschedule_uploadedschedule"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE 'teacher_id'")
        column_exists = cursor.fetchone() is not None

    if column_exists:
        schema_editor.execute(
            f"ALTER TABLE {table_name} DROP COLUMN teacher_id"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("sds", "0018_student_must_change_password_and_more"),
        ("teacherschedule", "0002_scheduleentry_lecture_time"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_teacher_column_if_missing,
                    reverse_code=drop_teacher_column_if_present,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="uploadedschedule",
                    name="teacher",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="uploaded_schedules",
                        to="sds.teacheradmin",
                    ),
                ),
            ],
        ),
    ]
