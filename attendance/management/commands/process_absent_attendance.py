from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from attendance.services import process_absent_attendance


class Command(BaseCommand):
    help = "Create absent attendance records for students who never checked in; SMS sends only when enabled."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="target_date",
            help="Date to process in YYYY-MM-DD format. Defaults to today.",
        )

    def handle(self, *args, **options):
        raw_date = options.get("target_date")

        if raw_date:
            try:
                target_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("Use --date in YYYY-MM-DD format.") from exc
        else:
            target_date = None

        try:
            created_count = process_absent_attendance(target_date=target_date, allow_today=True)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Processed absent attendance records: {created_count}")
        )
