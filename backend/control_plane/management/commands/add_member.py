from allauth.account.models import EmailAddress
from django.core.management.base import BaseCommand, CommandError, CommandParser

from control_plane.models import Membership, Role, Tenant, User


class Command(BaseCommand):
    help = "Give a user a role in a school, creating the user if needed (development helper)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--tenant", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument("--role", required=True, choices=Role.values)
        parser.add_argument("--password", help="Only for new users; otherwise they reset it")

    def handle(self, *args: object, **options: object) -> None:
        try:
            tenant = Tenant.objects.get(slug=options["tenant"])
        except Tenant.DoesNotExist as exc:
            raise CommandError("Unknown school") from exc
        email = str(options["email"]).lower()
        user = User.objects.filter(email=email).first()
        if user is None:
            password = options["password"]
            user = User.objects.create_user(email, password=str(password) if password else None)
            if password:
                # Development shortcut: skip the verification email for seeded users.
                EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
        Membership.objects.get_or_create(user=user, tenant=tenant, role=options["role"])
        self.stdout.write(self.style.SUCCESS(f"{email} is {options['role']} at {tenant.slug}"))
