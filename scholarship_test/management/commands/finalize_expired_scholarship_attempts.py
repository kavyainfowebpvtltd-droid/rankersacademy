from django.core.management.base import BaseCommand, CommandError

from scholarship_test.models import ScholarshipTest
from scholarship_test.services import test_service


class Command(BaseCommand):
    help = "Finalize expired scholarship test attempts so scores/results are stored in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--test-id",
            type=int,
            dest="test_id",
            help="Finalize attempts only for the specified scholarship test id.",
        )

    def handle(self, *args, **options):
        test_id = options.get("test_id")
        selected_test = None

        if test_id:
            try:
                selected_test = ScholarshipTest.objects.get(id=test_id)
            except ScholarshipTest.DoesNotExist as exc:
                raise CommandError(f"Scholarship test with id {test_id} was not found.") from exc

        finalized_attempts = test_service.finalize_expired_attempts(selected_test)

        if selected_test:
            message = (
                f"Finalized {len(finalized_attempts)} expired attempt(s) "
                f"for test '{selected_test.name}' (id={selected_test.id})."
            )
        else:
            message = f"Finalized {len(finalized_attempts)} expired scholarship attempt(s)."

        self.stdout.write(self.style.SUCCESS(message))
