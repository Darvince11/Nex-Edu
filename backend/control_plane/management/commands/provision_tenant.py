from django.core.management.base import BaseCommand, CommandParser

from control_plane.provisioning.service import provision_tenant


class Command(BaseCommand):
    help = "Create a new school: database, credentials, data key, schema and seed data."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--slug", required=True, help="Subdomain, e.g. greenfield")
        parser.add_argument("--name", required=True, help="Display name of the school")
        parser.add_argument("--canary", action="store_true", help="Receive migrations first")

    def handle(self, *args: object, **options: object) -> None:
        tenant = provision_tenant(
            slug=str(options["slug"]), name=str(options["name"]), is_canary=bool(options["canary"])
        )
        self.stdout.write(self.style.SUCCESS(f"Provisioned {tenant.slug} ({tenant.db_alias})"))
