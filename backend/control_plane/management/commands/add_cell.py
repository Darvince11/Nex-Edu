from django.core.management.base import BaseCommand, CommandParser

from control_plane.models import Cell
from control_plane.secrets import get_secrets_backend


class Command(BaseCommand):
    help = "Register a database cell (an Aurora cluster plus its PgBouncer) for new schools."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--name", required=True)
        parser.add_argument("--db-host", required=True, help="Writer endpoint for admin DDL")
        parser.add_argument("--db-port", type=int, default=5432)
        parser.add_argument("--pooler-host", required=True, help="PgBouncer endpoint for the app")
        parser.add_argument("--pooler-port", type=int, default=6432)
        parser.add_argument("--capacity", type=int, default=25)
        parser.add_argument("--region", default="af-south-1")
        parser.add_argument(
            "--admin-secret-ref",
            required=True,
            help="Secret holding the cell admin login as {USER, PASSWORD}",
        )
        parser.add_argument(
            "--store-admin-credentials",
            nargs=2,
            metavar=("USER", "PASSWORD"),
            help="Local development only: write the admin login to the secrets backend",
        )

    def handle(self, *args: object, **o: object) -> None:
        if o["store_admin_credentials"]:
            user, password = o["store_admin_credentials"]  # type: ignore[misc]
            get_secrets_backend().put(
                str(o["admin_secret_ref"]), {"USER": user, "PASSWORD": password}
            )
        cell, created = Cell.objects.update_or_create(
            name=o["name"],
            defaults={
                "db_host": o["db_host"],
                "db_port": o["db_port"],
                "pooler_host": o["pooler_host"],
                "pooler_port": o["pooler_port"],
                "capacity": o["capacity"],
                "region": o["region"],
                "admin_secret_ref": o["admin_secret_ref"],
            },
        )
        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} cell {cell}"))
