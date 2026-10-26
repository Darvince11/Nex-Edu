from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from control_plane.models import PlatformStaff, SchoolRegistration, User
from control_plane.registrations import approve_registration, reject_registration


class Command(BaseCommand):
    help = (
        "Review school registrations. Until the Super Admin console exists, this is how "
        "platform staff approve (creates the school and makes the applicant its owner) or reject."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        action = parser.add_mutually_exclusive_group(required=True)
        action.add_argument("--list", action="store_true", help="Show registrations under review")
        action.add_argument("--approve", metavar="ID")
        action.add_argument("--reject", metavar="ID")
        parser.add_argument("--reviewer", help="Email of the platform staff member deciding")
        parser.add_argument("--note", default="", help="Reason; sent to the applicant on rejection")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["list"]:
            pending = SchoolRegistration.objects.filter(
                status=SchoolRegistration.Status.PENDING
            ).select_related("owner")
            for r in pending.order_by("created_at"):
                flag = "  [POSSIBLE DUPLICATE]" if r.possible_duplicate else ""
                self.stdout.write(
                    f"{r.pk}  {r.school_name} ({r.slug}) {r.get_region_display()}, {r.town}  "
                    f"{r.owner.email} {r.phone}  ~{r.expected_pupils} pupils{flag}"
                )
            if not pending:
                self.stdout.write("No registrations are waiting for review.")
            return

        reviewer = self._reviewer(options["reviewer"])
        registration_id = options["approve"] or options["reject"]
        try:
            registration = SchoolRegistration.objects.select_related("owner").get(
                pk=registration_id
            )
        except (SchoolRegistration.DoesNotExist, ValidationError) as exc:
            raise CommandError("No registration with that ID.") from exc

        try:
            if options["approve"]:
                tenant = approve_registration(registration, reviewer=reviewer, note=options["note"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Approved: {tenant.slug} is live; {registration.owner.email} is its owner."
                    )
                )
            else:
                if not options["note"].strip():
                    raise CommandError("--note is required when rejecting; the applicant sees it.")
                reject_registration(registration, reviewer=reviewer, note=options["note"])
                self.stdout.write(self.style.WARNING(f"Rejected: {registration.school_name}."))
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

    def _reviewer(self, email: str | None) -> User | None:
        if not email:
            return None
        staff = (
            PlatformStaff.objects.filter(user__email=email.strip().lower(), is_active=True)
            .select_related("user")
            .first()
        )
        if staff is None:
            raise CommandError(f"{email} is not active platform staff.")
        return staff.user
