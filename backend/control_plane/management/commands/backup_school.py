from django.core.management.base import BaseCommand, CommandParser

from control_plane.backup import backup
from control_plane.models import Tenant


class Command(BaseCommand):
    help = "Back up one school (every record and file) to a zip under its own storage prefix."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--slug", required=True)

    def handle(self, *args: object, **options: object) -> None:
        tenant = Tenant.objects.get(slug=options["slug"])
        self.stdout.write(self.style.SUCCESS(f"Backed up {tenant.slug}: {backup(tenant)}"))
