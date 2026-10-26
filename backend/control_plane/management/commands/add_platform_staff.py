from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from control_plane.audit import record_platform_event
from control_plane.models import PlatformRole, PlatformStaff, User


class Command(BaseCommand):
    help = (
        "Grant or revoke a Nex Edu platform role. This is the only way to create platform "
        "staff: public registration and school invitations never can."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--role", choices=PlatformRole.values)
        parser.add_argument("--revoke", action="store_true")
        parser.add_argument("--reason", required=True, help="Recorded in the platform audit log")

    def handle(self, *args: Any, **options: Any) -> None:
        email = options["email"].strip().lower()
        with transaction.atomic():
            if options["revoke"]:
                staff = PlatformStaff.objects.filter(user__email=email, is_active=True).first()
                if staff is None:
                    raise CommandError(f"{email} has no active platform role.")
                staff.is_active = False
                staff.save(update_fields=["is_active"])
                action = "platform_staff.revoked"
            else:
                if not options["role"]:
                    raise CommandError("--role is required unless --revoke is given.")
                # A new account has no password: the person sets one with "Forgot password".
                user = User.objects.filter(email=email).first() or User.objects.create_user(
                    email, password=None
                )
                staff, _ = PlatformStaff.objects.update_or_create(
                    user=user, defaults={"role": options["role"], "is_active": True}
                )
                action = "platform_staff.granted"
            record_platform_event(
                action=action,
                target=staff,
                data={"email": email, "role": staff.role, "via": "manage.py"},
                reason=options["reason"],
            )
        self.stdout.write(self.style.SUCCESS(f"{action}: {email} ({staff.role})"))
