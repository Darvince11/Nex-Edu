"""The guardian directory: every parent and guardian, each listed once.

A guardian is stored once per child (``StudentGuardian``). The directory groups
those rows into people: by their Nex Edu login, otherwise by phone number,
otherwise by email. Inviting someone from the directory gives them a parent
login *and* links it to every child they're listed for, so they see their
children straight away.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from rest_framework.exceptions import ValidationError

from control_plane.members import invite_member
from control_plane.models import Role
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from integrations.phone import normalize_gh_phone

from .models import Student, StudentGuardian


def _key(g: StudentGuardian) -> str:
    if g.guardian_user_id:
        return f"user:{g.guardian_user_id}"
    phone = normalize_gh_phone(g.phone)
    if phone:
        return f"phone:{phone}"
    if g.email:
        return f"email:{g.email.lower()}"
    return f"row:{g.pk}"


def directory(
    students: QuerySet[Student], q: str = "", arm: str | None = None
) -> list[dict[str, Any]]:
    rows = StudentGuardian.objects.filter(student__in=students).select_related(
        "student__arm__level"
    )
    if arm:
        rows = rows.filter(student__arm_id=arm)
    if q:
        rows = rows.filter(
            Q(full_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(email__icontains=q)
            | Q(student__first_name__icontains=q)
            | Q(student__last_name__icontains=q)
        )
    people: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for g in rows.order_by("full_name", "pk"):
        key = _key(g)
        person = people.setdefault(
            key,
            {
                "key": key,
                "name": g.full_name,
                "phone": g.phone,
                "email": g.email,
                "has_login": bool(g.guardian_user_id),
                "receives_sms": g.receives_sms,
                "children": [],
            },
        )
        person["name"] = person["name"] or g.full_name
        person["email"] = person["email"] or g.email
        person["phone"] = person["phone"] or g.phone
        person["has_login"] = person["has_login"] or bool(g.guardian_user_id)
        person["children"].append(
            {
                "id": str(g.student_id),
                "name": g.student.full_name,
                "class": str(g.student.arm) if g.student.arm_id else "",
                "relationship": g.relationship,
            }
        )
    # Guardians with a login: their account is the reliable name and email; the
    # guardian rows may have been typed differently by the office.
    from control_plane.models import User

    accounts = {
        str(u.pk): u
        for u in User.objects.filter(
            pk__in=[k.split(":", 1)[1] for k in people if k.startswith("user:")]
        )
    }
    for key, person in people.items():
        account = accounts.get(key.split(":", 1)[1]) if key.startswith("user:") else None
        if account is not None:
            person["name"] = account.get_full_name() or person["name"]
            person["email"] = account.email or person["email"]
            person["phone"] = person["phone"] or account.phone
    return list(people.values())


def invite(
    *, request: Any, granter_roles: frozenset[str], students: QuerySet[Student], key: str
) -> int:
    """Give the guardian with this directory key a parent login, linked to their children."""
    rows = [g for g in StudentGuardian.objects.filter(student__in=students) if _key(g) == key]
    if not rows:
        raise ValidationError({"key": "This guardian wasn't found."})
    if any(g.guardian_user_id for g in rows):
        raise ValidationError({"key": "This guardian already has a Nex Edu login."})
    email = next((g.email for g in rows if g.email), "")
    if not email:
        raise ValidationError({"key": "Add an email address for this guardian first."})
    name = next((g.full_name for g in rows if g.full_name), "")
    first, _, last = name.partition(" ")
    membership = invite_member(
        request=request,
        tenant=require_tenant(),
        granter_roles=granter_roles,
        email=email,
        role=Role.PARENT,
        first_name=first,
        last_name=last,
        phone=next((g.phone for g in rows if g.phone), ""),
    )
    linked = 0
    with tenant_atomic():
        for g in rows:
            try:
                with transaction.atomic(using=require_tenant().db_alias):
                    g.guardian_user_id = membership.user_id
                    g.save(update_fields=["guardian_user_id"])
                    linked += 1
            except IntegrityError:  # the same login is already linked to this child
                g.delete()
        record_event(
            action="students.guardian_invited",
            request=request,
            after={"email": email, "children": linked},
        )
    return linked
