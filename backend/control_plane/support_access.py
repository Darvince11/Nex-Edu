"""Support access: the proprietor lets Nex Edu support see the school's set-up.

Nex Edu staff never see pupils' records (owner's rule). A grant shows support
only how the school is configured: profile, terms, classes with pupil counts,
subjects, modules, staff accounts and the set-up checklist. No pupil, guardian,
score, attendance mark or payment is ever read. Grants last at most 7 days, the
proprietor can end one at any time, and every look is recorded and shown to them.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from control_plane.audit import record_platform_event
from control_plane.models import Membership, Role, SupportGrant, SupportView, Tenant
from control_plane.tenancy import tenant_context

MAX_HOURS = 24 * 7


def active_grant(tenant: Tenant) -> SupportGrant | None:
    return (
        SupportGrant.objects.filter(
            tenant=tenant, revoked_at__isnull=True, expires_at__gt=timezone.now()
        )
        .select_related("granted_by")
        .first()
    )


@transaction.atomic
def grant(*, request: Any, tenant: Tenant, hours: int, reason: str) -> SupportGrant:
    if not 1 <= hours <= MAX_HOURS:
        raise ValidationError({"hours": "Between 1 hour and 7 days."})
    if not reason.strip():
        raise ValidationError({"reason": "Say what support should look at."})
    SupportGrant.objects.filter(
        tenant=tenant, revoked_at__isnull=True, expires_at__gt=timezone.now()
    ).update(revoked_at=timezone.now())
    item = SupportGrant.objects.create(
        tenant=tenant,
        granted_by=request.user,
        reason=reason.strip(),
        expires_at=timezone.now() + dt.timedelta(hours=hours),
    )
    record_platform_event(
        action="support.access_granted",
        request=request,
        tenant=tenant,
        target=item,
        data={"hours": hours},
        reason=item.reason,
    )
    return item


@transaction.atomic
def revoke(*, request: Any, item: SupportGrant) -> SupportGrant:
    if item.revoked_at is None and item.expires_at > timezone.now():
        item.revoked_at = timezone.now()
        item.save(update_fields=["revoked_at"])
        record_platform_event(
            action="support.access_revoked", request=request, tenant=item.tenant, target=item
        )
    return item


def configuration(*, request: Any, tenant: Tenant) -> dict[str, Any]:
    """The school's set-up, for support staff while a grant is open. Recorded."""
    item = active_grant(tenant)
    if item is None:
        raise PermissionDenied("The proprietor hasn't given Nex Edu support access to this school.")
    if tenant.status != Tenant.Status.ACTIVE:
        raise PermissionDenied("Only an active school can be looked at.")
    SupportView.objects.create(grant=item, staff=request.user)
    record_platform_event(
        action="support.configuration_viewed", request=request, tenant=tenant, target=item
    )
    from apps.academics.models import AcademicSession, ClassArm, Subject, Term
    from apps.school.models import SchoolProfile
    from apps.school.setup import progress
    from apps.students.models import Student
    from control_plane.modules import catalogue

    with tenant_context(tenant):
        profile = SchoolProfile.load()
        session = AcademicSession.objects.filter(is_current=True).first()
        term = Term.objects.filter(is_current=True).select_related("session").first()
        year_name, term_name = str(session or ""), str(term or "")
        arms = (
            ClassArm.objects.select_related("level")
            .annotate(pupils=Count("students", filter=Q(students__status=Student.Status.ACTIVE)))
            .order_by("level__order", "name")
        )
        classes = [{"name": str(a), "pupils": a.pupils} for a in arms]
        subjects = list(Subject.objects.order_by("name").values_list("name", flat=True))
        done, total, left = progress(tenant)
    staff: dict[str, dict[str, Any]] = {}
    for m in (
        Membership.objects.filter(tenant=tenant, is_active=True)
        .exclude(role__in=[Role.PARENT, Role.STUDENT])
        .select_related("user")
    ):
        row = staff.setdefault(
            str(m.user_id),
            {
                "name": m.user.get_full_name() or m.user.email,
                "email": m.user.email,
                "roles": [],
                "last_sign_in": m.user.last_login,
            },
        )
        row["roles"].append(m.get_role_display())
    return {
        "grant": {
            "reason": item.reason,
            "expires_at": item.expires_at,
            "granted_by": item.granted_by.get_full_name() or item.granted_by.email,
        },
        "profile": {
            "name": profile.name,
            "address": profile.address,
            "phone": profile.phone,
            "has_logo": bool(profile.logo),
            "terms_accepted": profile.terms_accepted_at is not None,
        },
        "year": year_name,
        "term": term_name,
        "classes": classes,
        "subjects": subjects,
        "modules": [
            {"name": m["name"], "active": m["active"]} for m in catalogue(tenant) if not m["core"]
        ],
        "staff": sorted(staff.values(), key=lambda r: r["name"]),
        "setup": {"done": done, "total": total, "left": left},
    }


def history(tenant: Tenant) -> list[dict[str, Any]]:
    """What the proprietor sees: each grant and every look under it."""
    now = timezone.now()
    return [
        {
            "id": str(g.pk),
            "reason": g.reason,
            "granted_by": g.granted_by.get_full_name() or g.granted_by.email,
            "created_at": g.created_at,
            "expires_at": g.expires_at,
            "revoked_at": g.revoked_at,
            "open": g.revoked_at is None and g.expires_at > now,
            "views": [
                {"staff": v.staff.get_full_name() or v.staff.email, "at": v.at}
                for v in g.views.select_related("staff")[:50]
            ],
        }
        for g in SupportGrant.objects.filter(tenant=tenant).select_related("granted_by")[:20]
    ]
