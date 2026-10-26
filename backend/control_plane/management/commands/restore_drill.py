import json

from django.core.management.base import BaseCommand, CommandError, CommandParser

from control_plane.backup import drill
from control_plane.models import Tenant


class Command(BaseCommand):
    help = "Back up a school, restore it as a throwaway copy, compare every table, clean up."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--slug", required=True)

    def handle(self, *args: object, **options: object) -> None:
        result = drill(Tenant.objects.get(slug=options["slug"]))
        self.stdout.write(json.dumps(result, indent=2))
        if not result["passed"]:
            raise CommandError("The restore drill found differences.")
        self.stdout.write(self.style.SUCCESS("Restore drill passed."))
