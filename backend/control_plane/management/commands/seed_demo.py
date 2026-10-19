"""Create a realistic demo school for local previews. Refuses to run unless DEBUG."""

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from control_plane.models import Membership, Role, Tenant, User
from control_plane.provisioning.service import provision_tenant
from control_plane.tenancy import tenant_context

DEMO_PASSWORD = "NexEdu-demo-2026!"  # noqa: S105 - local demo only; command refuses without DEBUG
FIRST = [
    "Kwame",
    "Ama",
    "Kofi",
    "Akua",
    "Yaw",
    "Abena",
    "Kwabena",
    "Efua",
    "Kojo",
    "Adwoa",
    "Kwaku",
    "Esi",
    "Fiifi",
    "Afia",
    "Nana",
    "Yaa",
    "Ekow",
    "Araba",
    "Selorm",
    "Dzifa",
]
LAST = [
    "Mensah",
    "Boateng",
    "Asante",
    "Owusu",
    "Osei",
    "Agyeman",
    "Darko",
    "Addo",
    "Ofori",
    "Quaye",
    "Tetteh",
    "Amoah",
    "Ansah",
    "Frimpong",
    "Badu",
    "Appiah",
]

STAFF = [
    ("owner@greenfield.test", Role.OWNER, "Esther", "Adjei"),
    ("head@greenfield.test", Role.PRINCIPAL, "Samuel", "Ofori"),
    ("bursar@greenfield.test", Role.BURSAR, "Gifty", "Amoah"),
    ("teacher@greenfield.test", Role.FORM_TEACHER, "Daniel", "Tetteh"),
]


def _user(email: str, first: str, last: str, phone: str = "") -> User:
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(
            email, DEMO_PASSWORD, first_name=first, last_name=last, phone=phone
        )
    EmailAddress.objects.update_or_create(
        user=user, email=email, defaults={"verified": True, "primary": True}
    )
    return user


class Command(BaseCommand):
    help = "Create the greenfield demo school: staff, students, results, fees (DEBUG only)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--slug", default="greenfield")

    def handle(self, *args: object, **options: object) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG on. Never use it in production.")
        slug = str(options["slug"])
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError(f"School '{slug}' already exists. Delete backend/var to start over.")

        rng = random.Random(42)  # noqa: S311 - reproducible demo data, not security
        tenant = provision_tenant(slug=slug, name="Greenfield Academy", is_canary=True)
        staff = {role: _user(email, first, last) for email, role, first, last in STAFF}
        for role, user in staff.items():
            Membership.objects.get_or_create(user=user, tenant=tenant, role=role)
        teacher = staff[Role.FORM_TEACHER]
        Membership.objects.get_or_create(user=teacher, tenant=tenant, role=Role.TEACHER)
        parent = _user("parent@greenfield.test", "Akosua", "Mensah", "+233244123456")
        Membership.objects.get_or_create(user=parent, tenant=tenant, role=Role.PARENT)

        with tenant_context(tenant):
            self._populate(tenant, staff, teacher, parent, rng)

        self.stdout.write(self.style.SUCCESS("\nDemo school 'Greenfield Academy' is ready.\n"))
        self.stdout.write(f"Password for every demo login: {DEMO_PASSWORD}\n")
        for email, role, *_ in STAFF:
            self.stdout.write(f"  {Role(role).label:<22} {email}")
        self.stdout.write(f"  {'Parent':<22} parent@greenfield.test  (no MFA needed)\n")
        self.stdout.write("Staff are asked to set up an authenticator app or passkey on first use.")

    def _populate(
        self, tenant: Tenant, staff: dict, teacher: User, parent: User, rng: random.Random
    ) -> None:
        from apps.academics.models import (
            AcademicSession,
            ClassArm,
            Subject,
            TeachingAssignment,
            Term,
        )
        from apps.assessments.models import AssessmentComponent, Score
        from apps.assessments.services import compute_results, publish_results
        from apps.attendance.models import AttendanceRecord
        from apps.communication.models import Announcement
        from apps.communication.services import publish_announcement
        from apps.finance.models import FeeItem, FeeSchedule, PaymentSettings
        from apps.finance.services import generate_invoices, record_manual_payment
        from apps.school.models import SchoolProfile
        from apps.students.models import StudentGuardian
        from apps.students.services import create_student

        profile = SchoolProfile.load()
        profile.motto, profile.address = "Knowledge, Discipline, Service", "East Legon, Accra"
        profile.phone, profile.principal_name, profile.admission_prefix = (
            "+233302123456",
            "Samuel Ofori",
            "GFA",
        )
        profile.save()

        today = timezone.localdate()
        session = AcademicSession.objects.create(
            name=f"{today.year}/{today.year + 1}",
            starts_on=today - dt.timedelta(days=45),
            ends_on=today + dt.timedelta(days=300),
            is_current=True,
        )
        term = Term.objects.create(
            session=session,
            number=1,
            starts_on=today - dt.timedelta(days=40),
            ends_on=today + dt.timedelta(days=45),
            next_term_begins=today + dt.timedelta(days=70),
            is_current=True,
        )

        arms = {a.level.name: a for a in ClassArm.objects.select_related("level")}
        subjects = {s.code: s for s in Subject.objects.all()}
        jhs_codes = ["ENG", "MTH", "SCI", "SOC", "RME", "ICT", "CT", "CAD"]
        jhs1 = arms["JHS 1"]
        TeachingAssignment.objects.create(
            teacher_user_id=teacher.pk, arm=jhs1, is_form_teacher=True
        )
        for code in jhs_codes:
            TeachingAssignment.objects.create(
                teacher_user_id=teacher.pk, arm=jhs1, subject=subjects[code]
            )

        students = []
        for level, count in (("JHS 1", 12), ("JHS 2", 8), ("Basic 6", 8)):
            for _ in range(count):
                first, last = rng.choice(FIRST), rng.choice(LAST)
                student = create_student(
                    request=None,
                    data={
                        "first_name": first,
                        "last_name": last,
                        "date_of_birth": today
                        - dt.timedelta(
                            days=365 * (13 if "JHS" in level else 11) + rng.randint(0, 300)
                        ),
                        "gender": rng.choice(["male", "female"]),
                        "arm": arms[level],
                        "hometown": rng.choice(["Kumasi", "Cape Coast", "Ho", "Tamale", "Accra"]),
                    },
                    guardians=[
                        {
                            "full_name": f"{rng.choice(FIRST)} {last}",
                            "phone": f"+23324{rng.randint(1000000, 9999999)}",
                            "relationship": "parent",
                            "is_primary": True,
                        }
                    ],
                )
                students.append(student)
        child = students[0]
        StudentGuardian.objects.filter(student=child).update(
            guardian_user_id=parent.pk, phone=parent.phone
        )

        # Three weeks of registers for JHS 1.
        day = today - dt.timedelta(days=21)
        while day <= today:
            if day.weekday() < 5:
                for s in students[:12]:
                    status = rng.choices(["present", "late", "absent"], [90, 6, 4])[0]
                    AttendanceRecord.objects.create(
                        student=s,
                        arm=jhs1,
                        term=term,
                        date=day,
                        status=status,
                        recorded_by=teacher.pk,
                        recorded_at=timezone.now(),
                        parent_notified=True,
                    )
            day += dt.timedelta(days=1)

        components = {c.code: c for c in AssessmentComponent.objects.all()}
        for s in students[:12]:
            ability = rng.uniform(0.45, 0.95)
            for code in jhs_codes:
                cs = Decimal(min(30, round(30 * ability + rng.uniform(-4, 4)))).max(Decimal(0))
                exam = Decimal(min(70, round(70 * ability + rng.uniform(-10, 10)))).max(Decimal(0))
                for comp, value in (("CS", cs), ("EXAM", exam)):
                    Score.objects.create(
                        student=s,
                        subject=subjects[code],
                        term=term,
                        component=components[comp],
                        score=value,
                        entered_by=teacher.pk,
                    )
        compute_results(request=None, arm=jhs1, term=term)
        publish_results(request=None, arm=jhs1, term=term)

        tuition, pta, ict = (
            FeeItem.objects.create(name=n) for n in ("Tuition", "PTA levy", "ICT fee")
        )
        for level, amount in (("JHS 1", 1500), ("JHS 2", 1500), ("Basic 6", 1100)):
            FeeSchedule.objects.create(
                term=term, level=arms[level].level, item=tuition, amount_pesewas=amount * 100
            )
        FeeSchedule.objects.create(term=term, item=pta, amount_pesewas=80 * 100)
        FeeSchedule.objects.create(term=term, item=ict, amount_pesewas=120 * 100)
        generate_invoices(request=None, term=term, due_date=today + dt.timedelta(days=14))
        from apps.finance.models import Invoice

        for invoice in Invoice.objects.order_by("number")[:6]:
            record_manual_payment(
                request=None,
                invoice=invoice,
                amount_pesewas=invoice.total_pesewas // 2,
                method="cash",
                reference="",
            )
        PaymentSettings.objects.filter(pk=1).update(online_payments_enabled=True)

        announcement = Announcement.objects.create(
            title="Mid-term break",
            body="School closes on Friday at 12 noon and resumes on Monday.",
            audience=Announcement.Audience.EVERYONE,
            created_by=staff[Role.PRINCIPAL].pk,
        )
        publish_announcement(request=None, announcement=announcement)
