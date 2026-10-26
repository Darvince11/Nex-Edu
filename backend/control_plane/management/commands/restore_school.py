from django.core.management.base import BaseCommand, CommandError, CommandParser

from control_plane import backup
from control_plane.models import Tenant


class Command(BaseCommand):
    help = (
        "Restore one school from its backup zip: in place (replaces that school's database) "
        "or as a copy nobody can open, for checking."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--from", dest="source", required=True, help="Zip path or storage key")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--in-place", dest="slug", help="The school to replace")
        group.add_argument("--copy-as", dest="copy", help="Web address for a throwaway copy")
        parser.add_argument(
            "--yes-replace", action="store_true", help="Confirm replacing the school's data"
        )

    def handle(self, *args: object, **options: object) -> None:
        source = str(options["source"])
        if options["slug"]:
            if not options["yes_replace"]:
                raise CommandError("This replaces the school's data. Add --yes-replace to go on.")
            tenant = backup.restore_in_place(Tenant.objects.get(slug=options["slug"]), source)
            self.stdout.write(self.style.SUCCESS(f"Restored {tenant.slug} in place."))
        else:
            copy = backup.restore_copy(source, slug=str(options["copy"]), name="Restored copy")
            total = sum(backup.counts(copy).values())
            self.stdout.write(
                self.style.SUCCESS(f"Restored a copy as {copy.slug}: {total} records.")
            )
