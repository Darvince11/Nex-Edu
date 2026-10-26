"""The set-up checklist a new school works through after approval.

Each step is checked against the school's own data, so it ticks itself off when
the work is really done (wherever it was done). Steps say who can do them; the
API still checks every action on the page the step links to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.utils import timezone

from core.rbac import Perm


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    description: str
    href: str
    perms: tuple[str, ...]  # any of these lets someone do it
    who: str
    module: str = ""  # only listed while this module is switched on


STEPS: tuple[Step, ...] = (
    Step(
        "profile",
        "Complete the school profile",
        "Address, phone and the head teacher's name, as they appear on report cards and receipts.",
        "/settings",
        (Perm.SCHOOL_MANAGE,),
        "Proprietor, head teacher or administrator",
    ),
    Step(
        "logo",
        "Add the school logo",
        "Shown on every page, report cards, receipts and the admission form.",
        "/settings",
        (Perm.SCHOOL_BRANDING,),
        "Proprietor",
    ),
    Step(
        "terms",
        "Accept the terms for the school",
        "The terms of service and privacy notice, accepted once on behalf of the school.",
        "",
        (Perm.SCHOOL_LEGAL,),
        "Proprietor",
    ),
    Step(
        "modules",
        "Choose your modules",
        "Switch on the optional features the school uses: online admissions, fees, SMS.",
        "/settings/modules",
        (Perm.SCHOOL_MODULES,),
        "Proprietor",
    ),
    Step(
        "year",
        "Set the academic year and current term",
        "Registers, fees and report cards all follow the current term.",
        "/academics",
        (Perm.ACADEMICS_MANAGE,),
        "Proprietor, head teacher or administrator",
    ),
    Step(
        "fees",
        "Set this term's fees",
        "What each class pays this term, so invoices can go to parents.",
        "/fees",
        (Perm.FINANCE_MANAGE,),
        "Proprietor or bursar",
        module="fees",
    ),
    Step(
        "staff",
        "Add staff",
        "Teachers and other staff get an email to set their password.",
        "/people",
        (Perm.MEMBERS_MANAGE, Perm.MEMBERS_MANAGE_STAFF),
        "Proprietor or head teacher",
    ),
    Step(
        "class_teachers",
        "Assign class teachers",
        "Each class teacher takes their class's register and prepares its report cards.",
        "/academics",
        (Perm.ACADEMICS_MANAGE,),
        "Proprietor, head teacher or administrator",
    ),
    Step(
        "pupils",
        "Add pupils",
        "One at a time or from a spreadsheet; each pupil joins their class straight away.",
        "/students",
        (Perm.STUDENTS_MANAGE,),
        "Proprietor, head teacher or administrator",
    ),
    Step(
        "parents",
        "Invite parents",
        "Parents see report cards, attendance and fees, and can pay online.",
        "/people",
        (Perm.MEMBERS_MANAGE, Perm.STUDENTS_MANAGE, Perm.ADMISSIONS_MANAGE),
        "Proprietor, head teacher or administrator",
    ),
)


def _done(tenant: Any) -> dict[str, bool]:
    """Which steps are finished. Runs inside the school's tenant context."""
    from apps.academics.models import AcademicSession, TeachingAssignment, Term
    from apps.finance.models import FeeSchedule
    from apps.students.models import Student
    from control_plane.models import Membership, Role
    from control_plane.modules import choices_confirmed

    from .models import SchoolProfile

    profile = SchoolProfile.load()
    term = Term.objects.filter(is_current=True).first()
    members = Membership.objects.filter(tenant=tenant, is_active=True)
    return {
        "modules": choices_confirmed(tenant),
        "profile": bool(profile.address and profile.phone and profile.principal_name),
        "logo": bool(profile.logo),
        "terms": profile.terms_accepted_at is not None,
        "year": bool(term) and AcademicSession.objects.filter(is_current=True).exists(),
        "fees": bool(term) and FeeSchedule.objects.filter(term=term).exists(),
        "staff": members.exclude(role__in=[Role.OWNER, Role.PARENT, Role.STUDENT]).exists(),
        "class_teachers": TeachingAssignment.objects.filter(is_form_teacher=True).exists(),
        "pupils": Student.objects.filter(status=Student.Status.ACTIVE).exists(),
        "parents": members.filter(role=Role.PARENT).exists(),
    }


def steps_for(tenant: Any) -> tuple[Step, ...]:
    """The steps that apply: a step tied to a switched-off module is left out."""
    from control_plane.modules import active_modules

    active = active_modules(tenant)
    return tuple(s for s in STEPS if not s.module or s.module in active)


def progress(tenant: Any) -> tuple[int, int, list[str]]:
    """(steps done, total steps, labels of steps left)."""
    done = _done(tenant)
    steps = steps_for(tenant)
    left = [s.label for s in steps if not done[s.key]]
    return len(steps) - len(left), len(steps), left


def checklist(tenant: Any, permissions: frozenset[str]) -> dict[str, Any]:
    from .models import SchoolProfile

    done = _done(tenant)
    profile = SchoolProfile.load()
    steps = [
        {
            "key": s.key,
            "label": s.label,
            "description": s.description,
            "href": s.href,
            "done": done[s.key],
            "can_do": any(p in permissions for p in s.perms),
            "who": s.who,
        }
        for s in steps_for(tenant)
    ]
    finished = sum(1 for s in steps if s["done"])
    return {
        "steps": steps,
        "done": finished,
        "total": len(steps),
        "complete": finished == len(steps),
        "hidden": profile.setup_hidden_at is not None,
        "terms_version": settings.TERMS_VERSION,
        "terms_accepted_by": profile.terms_accepted_by,
        "terms_accepted_at": profile.terms_accepted_at,
    }


def accept_terms(*, user: Any) -> None:
    from .models import SchoolProfile

    profile = SchoolProfile.load()
    profile.terms_accepted_at = timezone.now()
    profile.terms_accepted_by = user.email
    profile.terms_version = settings.TERMS_VERSION
    profile.save(
        update_fields=["terms_accepted_at", "terms_accepted_by", "terms_version", "updated_at"]
    )


def set_hidden(hidden: bool) -> None:
    from .models import SchoolProfile

    profile = SchoolProfile.load()
    profile.setup_hidden_at = timezone.now() if hidden else None
    profile.save(update_fields=["setup_hidden_at", "updated_at"])
