from django.core.management.base import BaseCommand, CommandError, CommandParser

from control_plane.migration_runner import MigrationResult, run_tenant_migrations
from control_plane.models import Tenant


class Command(BaseCommand):
    help = "Migrate school databases: canary schools first, then one cell at a time."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--tenant", action="append", default=[], help="Only these slugs")
        parser.add_argument("--cell", action="append", default=[], help="Only these cells")
        parser.add_argument("--parallel", type=int, default=None, help="Concurrent migrations")

    def handle(self, *args: object, **options: object) -> None:
        tenants = Tenant.objects.select_related("cell").filter(
            status__in=[Tenant.Status.ACTIVE, Tenant.Status.SUSPENDED]
        )
        if options["tenant"]:
            tenants = tenants.filter(slug__in=options["tenant"])
        if options["cell"]:
            tenants = tenants.filter(cell__name__in=options["cell"])

        def report(index: int, results: list[MigrationResult]) -> None:
            ok = sum(r.succeeded for r in results)
            self.stdout.write(f"Wave {index + 1}: {ok}/{len(results)} schools migrated")
            for r in results:
                if not r.succeeded:
                    self.stderr.write(f"  FAILED {r.tenant.slug}: {r.error}")

        results = run_tenant_migrations(
            tenants.order_by("slug"),
            parallelism=options["parallel"],  # type: ignore[arg-type]
            on_wave=report,
        )
        failed = [r for r in results if not r.succeeded]
        if failed:
            raise CommandError(
                f"{len(failed)} school(s) failed. Rollout halted; later waves were not attempted."
            )
        self.stdout.write(self.style.SUCCESS(f"Migrated {len(results)} school database(s)."))
