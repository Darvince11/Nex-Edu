"""Reading the platform audit log for the console.

Events are filed under a school when they name it (``tenant_id``), concern its
registration, or concern one of its people (sign-ins, password resets,
authenticator changes). Events about nobody in particular stay "Platform".
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from control_plane.models import Membership, PlatformAuditEvent, SchoolRegistration, Tenant, User

PAGE = 50
USER_TYPE = User._meta.label_lower
REGISTRATION_TYPE = SchoolRegistration._meta.label_lower


def school_filter(tenant: Tenant) -> Q:
    member_ids = list(
        Membership.objects.filter(tenant=tenant).values_list("user_id", flat=True).distinct()
    )
    emails = list(User.objects.filter(pk__in=member_ids).values_list("email", flat=True))
    registration_ids = [
        str(pk)
        for pk in SchoolRegistration.objects.filter(tenant=tenant).values_list("pk", flat=True)
    ]
    return (
        Q(tenant_id=tenant.pk)
        | Q(target_type=REGISTRATION_TYPE, target_id__in=registration_ids)
        | Q(actor_id__in=member_ids)
        | Q(target_type=USER_TYPE, target_id__in=[str(i) for i in member_ids])
        | Q(action="auth.sign_in_failed", data__email__in=emails)
    )


def platform_only_filter() -> Q:
    """Events not tied to any school or school member (platform staff work, etc.)."""
    member_ids = list(Membership.objects.values_list("user_id", flat=True).distinct())
    member_emails = list(User.objects.filter(pk__in=member_ids).values_list("email", flat=True))
    return (
        Q(tenant_id__isnull=True)
        & ~Q(target_type=REGISTRATION_TYPE)
        & ~Q(actor_id__in=member_ids)
        & ~Q(target_type=USER_TYPE, target_id__in=[str(i) for i in member_ids])
        & ~Q(action="auth.sign_in_failed", data__email__in=member_emails)
    )


def _attribute(events: list[PlatformAuditEvent]) -> dict[int, list[dict[str, str]]]:
    """For each event, the schools it concerns."""
    tenants = {t.pk: t for t in Tenant.objects.all()}
    registrations = dict(
        SchoolRegistration.objects.filter(tenant__isnull=False).values_list("pk", "tenant_id")
    )
    registrations = {str(k): v for k, v in registrations.items()}
    user_ids: set[str] = set()
    emails: set[str] = set()
    for e in events:
        if e.actor_id:
            user_ids.add(str(e.actor_id))
        if e.target_type == USER_TYPE:
            user_ids.add(e.target_id)
        if e.action == "auth.sign_in_failed" and e.data:
            emails.add(str(e.data.get("email", "")))
    by_email = dict(User.objects.filter(email__in=emails).values_list("email", "pk"))
    user_ids |= {str(pk) for pk in by_email.values()}
    schools_of: dict[str, set[Any]] = defaultdict(set)
    for user_id, tenant_id in Membership.objects.filter(user_id__in=user_ids).values_list(
        "user_id", "tenant_id"
    ):
        schools_of[str(user_id)].add(tenant_id)

    result = {}
    for e in events:
        ids: set[Any] = set()
        if e.tenant_id:
            ids.add(e.tenant_id)
        if e.target_type == REGISTRATION_TYPE and e.target_id in registrations:
            ids.add(registrations[e.target_id])
        if e.actor_id:
            ids |= schools_of.get(str(e.actor_id), set())
        if e.target_type == USER_TYPE:
            ids |= schools_of.get(e.target_id, set())
        if e.action == "auth.sign_in_failed" and e.data and e.data.get("email") in by_email:
            ids |= schools_of.get(str(by_email[e.data["email"]]), set())
        result[e.seq] = sorted(
            ({"slug": tenants[i].slug, "name": tenants[i].name} for i in ids if i in tenants),
            key=lambda s: s["name"],
        )
    return result


def rows(queryset: QuerySet[PlatformAuditEvent], *, before: int | None = None) -> dict[str, Any]:
    """A page of events, newest first, with the schools each concerns."""
    if before:
        queryset = queryset.filter(seq__lt=before)
    page = list(queryset.order_by("-seq")[: PAGE + 1])
    more = len(page) > PAGE
    page = page[:PAGE]
    schools = _attribute(page)
    return {
        "events": [
            {
                "seq": e.seq,
                "occurred_at": e.occurred_at,
                "action": e.action,
                "actor_email": e.actor_email,
                "ip": e.ip,
                "reason": e.reason,
                "data": e.data or {},
                "target_type": e.target_type.rsplit(".", 1)[-1],
                "schools": schools.get(e.seq, []),
            }
            for e in page
        ],
        "next_before": page[-1].seq if more and page else None,
    }


def filtered(params: Any) -> QuerySet[PlatformAuditEvent]:
    events = PlatformAuditEvent.objects.all()
    school = params.get("school", "")
    if school == "platform":
        events = events.filter(platform_only_filter())
    elif school:
        tenant = Tenant.objects.filter(slug=school).first()
        events = events.filter(school_filter(tenant)) if tenant else events.none()
    if action := params.get("action"):
        events = events.filter(action__startswith=action)
    if actor := params.get("actor", "").strip().lower():
        events = events.filter(actor_email__icontains=actor)
    if (days := params.get("days", "")).isdigit():
        events = events.filter(occurred_at__gte=timezone.now() - dt.timedelta(days=int(days)))
    return events


def school_groups(days: int = 30) -> list[dict[str, Any]]:
    """Event counts per school (and for the platform itself) over the last ``days``."""
    since = timezone.now() - dt.timedelta(days=days)
    recent = PlatformAuditEvent.objects.filter(occurred_at__gte=since)
    groups = [
        {
            "slug": "platform",
            "name": "Platform (no school)",
            "events": recent.filter(platform_only_filter()).count(),
        }
    ]
    for tenant in Tenant.objects.order_by("name"):
        groups.append(
            {
                "slug": tenant.slug,
                "name": tenant.name,
                "events": recent.filter(school_filter(tenant)).count(),
            }
        )
    return groups
