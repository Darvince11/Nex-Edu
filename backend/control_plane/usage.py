"""Platform-wide figures for the Super Admin console.

Each school's database is read only by ``collect`` (a background job, or the
"Refresh figures" button), and only for totals: how many pupils, classes,
registers, messages and payments. Those totals are stored in ``TenantUsage``;
the console reads that table and the control plane, never a school's records.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX
from django.db.models import Count, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from control_plane.models import (
    GhanaRegion,
    Membership,
    PlatformAuditEvent,
    Role,
    SchoolRegistration,
    Tenant,
    TenantUsage,
)
from control_plane.pricing import band_dict, band_for, price_bands
from control_plane.tenancy import tenant_context

logger = logging.getLogger(__name__)

STALE_AFTER = dt.timedelta(hours=1)
QUIET_AFTER = dt.timedelta(days=14)
SETUP_GRACE = dt.timedelta(days=7)  # a new school has a week before unfinished set-up is flagged
SMS_WARNING_SHARE = 0.8
HISTORY_DAYS = 90
STAFF_ROLES = set(Role.values) - {Role.PARENT, Role.STUDENT}


# --- Collecting -------------------------------------------------------------------------


def _school_totals(today: dt.date, now: dt.datetime) -> dict[str, Any]:
    """Runs inside a school's tenant context. Counts only; nothing personal leaves."""
    from apps.academics.models import ClassArm, Term
    from apps.admissions.models import Application
    from apps.assessments.models import ReportCard
    from apps.attendance.models import AttendanceRecord
    from apps.communication.models import Channel, Delivery
    from apps.finance.models import Invoice, Payment
    from apps.students.models import Student
    from control_plane.subscriptions import sms_allowance
    from control_plane.tenancy import require_tenant
    from core.audit.models import AuditEvent

    paid = Payment.objects.filter(status=Payment.Status.SUCCESS)
    term = Term.objects.filter(is_current=True).first()
    owed = (
        Invoice.objects.filter(term=term)
        .exclude(status=Invoice.Status.VOID)
        .aggregate(billed=Sum("total_pesewas"), paid=Sum("paid_pesewas"))
        if term
        else {"billed": 0, "paid": 0}
    )
    return {
        "pupils": Student.objects.filter(status=Student.Status.ACTIVE).count(),
        "classes": ClassArm.objects.filter(level__is_active=True).count(),
        "applications_pending": Application.objects.filter(
            status__in=[Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW]
        ).count(),
        "registers_7d": AttendanceRecord.objects.filter(
            date__gte=today - dt.timedelta(days=6)
        ).count(),
        "report_cards_published": ReportCard.objects.filter(
            status=ReportCard.Status.PUBLISHED
        ).count(),
        "sms_sent_month": Delivery.objects.filter(
            channel=Channel.SMS,
            status=Delivery.Status.SENT,
            created_at__date__gte=today.replace(day=1),
        ).count(),
        "sms_monthly_limit": sms_allowance(require_tenant())["monthly"],
        "payments_30d_pesewas": paid.filter(paid_at__gte=now - dt.timedelta(days=30)).aggregate(
            s=Sum("amount_received_pesewas")
        )["s"]
        or 0,
        "payments_total_pesewas": paid.aggregate(s=Sum("amount_received_pesewas"))["s"] or 0,
        "outstanding_pesewas": (owed["billed"] or 0) - (owed["paid"] or 0),
        "last_activity_at": AuditEvent.objects.aggregate(last=Max("occurred_at"))["last"],
    }


def _people(tenant: Tenant, now: dt.datetime) -> dict[str, int]:
    members = Membership.objects.filter(tenant=tenant, is_active=True)
    users = members.values("user_id").distinct()
    return {
        "staff": members.filter(role__in=STAFF_ROLES).values("user_id").distinct().count(),
        "parents": members.filter(role=Role.PARENT).values("user_id").distinct().count(),
        "active_users_7d": users.filter(user__last_login__gte=now - dt.timedelta(days=7)).count(),
        "active_users_30d": users.filter(user__last_login__gte=now - dt.timedelta(days=30)).count(),
    }


def collect(tenant: Tenant) -> TenantUsage:
    """Refresh today's totals for one school."""
    now = timezone.now()
    today = timezone.localdate()
    from apps.school.setup import progress

    with tenant_context(tenant):
        totals = _school_totals(today, now)
        done, total, left = progress(tenant)
        totals |= {"setup_done": done, "setup_total": total, "setup_left": left}
    usage, _ = TenantUsage.objects.update_or_create(
        tenant=tenant,
        day=today,
        defaults={**totals, **_people(tenant, now), "collected_at": now},
    )
    return usage


def collect_many(slugs: list[str] | None = None) -> int:
    """Refresh every active school (or the given ones). One school failing doesn't stop the rest."""
    tenants = Tenant.objects.filter(status=Tenant.Status.ACTIVE)
    if slugs is not None:
        tenants = tenants.filter(slug__in=slugs)
    done = 0
    for tenant in tenants:
        try:
            collect(tenant)
            done += 1
        except Exception:
            logger.exception("Collecting usage for %s failed", tenant.slug)
    return done


def latest_usage(tenants: Any) -> dict[Any, TenantUsage]:
    """The newest totals for each school, in one query (works on SQLite and Postgres)."""
    newest = TenantUsage.objects.filter(tenant=OuterRef("tenant")).order_by("-day").values("pk")[:1]
    rows = TenantUsage.objects.filter(tenant__in=tenants, pk=Subquery(newest))
    return {row.tenant_id: row for row in rows}


def refresh_if_stale(tenants: Any) -> dict[Any, TenantUsage]:
    """Schools never counted are counted now; stale ones are refreshed in the background."""
    from control_plane.tasks import collect_usage
    from core.tasks import enqueue_after_commit

    latest = latest_usage(tenants)
    missing = [t for t in tenants if t.pk not in latest]
    for tenant in missing:
        try:
            latest[tenant.pk] = collect(tenant)
        except Exception:
            logger.exception("Collecting usage for %s failed", tenant.slug)
    stale = [
        t.slug
        for t in tenants
        if t.pk in latest
        and t not in missing
        and latest[t.pk].collected_at < timezone.now() - STALE_AFTER
    ]
    if stale:
        enqueue_after_commit(collect_usage, stale)
    return latest


# --- Reading -------------------------------------------------------------------------------


def _usage_dict(usage: TenantUsage | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    fields = [f.name for f in TenantUsage._meta.fields if f.name not in {"id", "tenant"}]
    return {name: getattr(usage, name) for name in fields}


def attention(tenant: Tenant, usage: TenantUsage | None, now: dt.datetime) -> list[str]:
    """Why this school may need a look, in plain words. Empty when all is well."""
    if usage is None:
        return ["No figures yet"]
    reasons = []
    if tenant.created_at < now - QUIET_AFTER and (
        usage.last_activity_at is None or usage.last_activity_at < now - QUIET_AFTER
    ):
        reasons.append("No activity for 14 days")
    if usage.active_users_30d == 0 and tenant.created_at < now - QUIET_AFTER:
        reasons.append("Nobody has signed in for 30 days")
    unfinished = usage.setup_total - usage.setup_done
    if unfinished > 0 and tenant.created_at < now - SETUP_GRACE:
        reasons.append(f"Set-up not finished ({unfinished} steps left)")
    if (
        usage.sms_monthly_limit
        and usage.sms_sent_month >= SMS_WARNING_SHARE * usage.sms_monthly_limit
    ):
        reasons.append("SMS allowance nearly used")
    return reasons


def school_rows(tenants: Any) -> list[dict[str, Any]]:
    """The schools list: identity, size, price band and last activity."""
    tenants = list(tenants.select_related("registration"))
    latest = refresh_if_stale([t for t in tenants if t.status == Tenant.Status.ACTIVE])
    now = timezone.now()
    bands = price_bands()
    rows = []
    for tenant in tenants:
        usage = latest.get(tenant.pk)
        registration = getattr(tenant, "registration", None)
        rows.append(
            {
                "id": tenant.pk,
                "slug": tenant.slug,
                "name": tenant.name,
                "status": tenant.status,
                "is_canary": tenant.is_canary,
                "created_at": tenant.created_at,
                "region": registration.get_region_display() if registration else "",
                "town": registration.town if registration else "",
                "pupils": usage.pupils if usage else None,
                "staff": usage.staff if usage else None,
                "active_users_7d": usage.active_users_7d if usage else None,
                "last_activity_at": usage.last_activity_at if usage else None,
                "band": band_dict(usage.pupils, bands) if usage else None,
                "attention": attention(tenant, usage, now)
                if tenant.status == Tenant.Status.ACTIVE
                else [],
            }
        )
    return rows


def _month_series(queryset: Any, field: str, months: int, today: dt.date) -> list[dict[str, Any]]:
    start = (today.replace(day=1) - dt.timedelta(days=31 * (months - 1))).replace(day=1)
    counts = {
        row["month"].date() if isinstance(row["month"], dt.datetime) else row["month"]: row["n"]
        for row in queryset.filter(**{f"{field}__date__gte": start})
        .annotate(month=TruncMonth(field))
        .values("month")
        .annotate(n=Count("pk"))
    }
    series, month = [], start
    while month <= today:
        series.append({"month": month.isoformat(), "count": counts.get(month, 0)})
        month = (month + dt.timedelta(days=32)).replace(day=1)
    return series


def overview() -> dict[str, Any]:
    """Everything on the console dashboard."""
    now = timezone.now()
    today = timezone.localdate()
    tenants = Tenant.objects.all()
    active = list(tenants.filter(status=Tenant.Status.ACTIVE))
    latest = refresh_if_stale(active)
    usages = [latest[t.pk] for t in active if t.pk in latest]

    def total(name: str) -> int:
        return sum(getattr(u, name) for u in usages)

    current_bands = price_bands()
    bands = {band.code: 0 for band in current_bands}
    for usage in usages:
        bands[band_for(usage.pupils, current_bands).code] += 1
    status_counts = dict(tenants.values_list("status").annotate(n=Count("pk")))

    history = (
        TenantUsage.objects.filter(
            tenant__in=active, day__gte=today - dt.timedelta(days=HISTORY_DAYS - 1)
        )
        .values("day")
        .annotate(pupils=Sum("pupils"), active_users=Sum("active_users_7d"), schools=Count("pk"))
        .order_by("day")
    )
    regions = dict(GhanaRegion.choices)
    by_region = (
        SchoolRegistration.objects.filter(tenant__in=active)
        .values("region")
        .annotate(n=Count("pk"))
        .order_by("-n")
    )
    at_risk = [
        {"slug": t.slug, "name": t.name, "reasons": reasons}
        for t in active
        if (reasons := attention(t, latest.get(t.pk), now))
    ]
    top = sorted(((t, latest[t.pk]) for t in active if t.pk in latest), key=lambda p: -p[1].pupils)[
        :5
    ]
    return {
        "generated_at": now,
        "schools": {
            "active": status_counts.get(Tenant.Status.ACTIVE, 0),
            "setting_up": status_counts.get(Tenant.Status.PROVISIONING, 0),
            "suspended": status_counts.get(Tenant.Status.SUSPENDED, 0),
            "failed": status_counts.get(Tenant.Status.FAILED, 0),
            "closed": status_counts.get(Tenant.Status.OFFBOARDED, 0),
            "active_7d": sum(
                1
                for u in usages
                if u.last_activity_at and u.last_activity_at >= now - dt.timedelta(days=7)
            ),
        },
        "registrations_pending": SchoolRegistration.objects.filter(
            status=SchoolRegistration.Status.PENDING
        ).count(),
        "people": {
            "pupils": total("pupils"),
            "staff": total("staff"),
            "parents": total("parents"),
            "active_users_7d": total("active_users_7d"),
            "active_users_30d": total("active_users_30d"),
        },
        "money": {
            "expected_subscriptions_pesewas": sum(
                band_for(u.pupils, current_bands).price_pesewas for u in usages
            ),
            "fees_processed_30d_pesewas": total("payments_30d_pesewas"),
            "fees_processed_total_pesewas": total("payments_total_pesewas"),
            "fees_outstanding_pesewas": total("outstanding_pesewas"),
        },
        "messages": {"sms_sent_month": total("sms_sent_month")},
        "bands": [
            {
                "code": band.code,
                "label": band.label,
                "price_pesewas": band.price_pesewas,
                "schools": bands[band.code],
            }
            for band in current_bands
        ],
        "history": [
            {
                "day": row["day"].isoformat(),
                "pupils": row["pupils"] or 0,
                "active_users": row["active_users"] or 0,
                "schools": row["schools"],
            }
            for row in history
        ],
        "schools_by_month": _month_series(tenants, "created_at", 12, today),
        "registrations_by_month": _month_series(
            SchoolRegistration.objects.all(), "created_at", 12, today
        ),
        "by_region": [
            {"region": regions.get(row["region"], row["region"]), "schools": row["n"]}
            for row in by_region
        ],
        "top_schools": [
            {"slug": t.slug, "name": t.name, "pupils": u.pupils, "staff": u.staff} for t, u in top
        ],
        "attention": at_risk,
    }


def _billing_summary(tenant: Tenant) -> dict[str, Any]:
    """Unpaid invoices, SMS and support access for the school's console page."""
    from control_plane.models import SubscriptionInvoice
    from control_plane.subscriptions import sms_allowance
    from control_plane.support_access import active_grant

    unpaid = SubscriptionInvoice.objects.filter(
        tenant=tenant, status=SubscriptionInvoice.Status.OPEN
    ).order_by("due_on")
    oldest = unpaid.first()
    grant = active_grant(tenant)
    return {
        "unpaid_pesewas": sum(i.total_pesewas for i in unpaid),
        "unpaid_invoices": unpaid.count(),
        "oldest_due_on": oldest.due_on if oldest else None,
        "sms": sms_allowance(tenant),
        "support_open_until": grant.expires_at if grant else None,
    }


def school_detail(tenant: Tenant, *, refresh: bool = False) -> dict[str, Any]:
    """One school as platform staff see it: who runs it, how it uses Nex Edu, what
    Nex Edu staff did to it. Counts only; no pupil or parent is named."""
    now = timezone.now()
    usage = None
    if tenant.status == Tenant.Status.ACTIVE:
        usage = latest_usage([tenant]).get(tenant.pk)
        if refresh or usage is None or usage.collected_at < now - STALE_AFTER:
            usage = collect(tenant)
    registration = (
        SchoolRegistration.objects.filter(tenant=tenant)
        .select_related("owner", "reviewed_by")
        .first()
    )
    members = Membership.objects.filter(tenant=tenant, is_active=True)
    owner_membership = (
        members.filter(role=Role.OWNER).select_related("user").order_by("created_at").first()
    )
    owner = (
        owner_membership.user
        if owner_membership
        else (registration.owner if registration else None)
    )
    by_role = dict(members.values_list("role").annotate(n=Count("pk")))
    from allauth.mfa.models import Authenticator

    staff_users = members.filter(role__in=STAFF_ROLES).values("user_id").distinct()
    with_app = (
        Authenticator.objects.filter(user_id__in=staff_users, type=Authenticator.Type.TOTP)
        .values("user_id")
        .distinct()
        .count()
    )
    # Invited but never set a password (invitations create an unusable one).
    not_joined = (
        members.filter(user__password__startswith=UNUSABLE_PASSWORD_PREFIX)
        .values("user_id")
        .distinct()
        .count()
    )
    last_sign_in = members.aggregate(last=Max("user__last_login"))["last"]
    history = TenantUsage.objects.filter(
        tenant=tenant, day__gte=timezone.localdate() - dt.timedelta(days=HISTORY_DAYS - 1)
    ).order_by("day")
    # Nex Edu staff actions on this school, including those on its registration
    # (recorded before the school existed).
    about_school = Q(tenant_id=tenant.pk)
    if registration:
        about_school |= Q(
            target_type=SchoolRegistration._meta.label_lower, target_id=str(registration.pk)
        )
    events = PlatformAuditEvent.objects.filter(about_school).order_by("-seq")[:15]
    return {
        "id": tenant.pk,
        "slug": tenant.slug,
        "name": tenant.name,
        "status": tenant.status,
        "is_canary": tenant.is_canary,
        "created_at": tenant.created_at,
        "schema_version": tenant.schema_version,
        "migrated_at": tenant.migrated_at,
        "cell": tenant.cell.name if tenant.cell_id else "",
        "registration": {
            "school_type": registration.get_school_type_display(),
            "region": registration.get_region_display(),
            "town": registration.town,
            "phone": registration.phone,
            "expected_pupils": registration.expected_pupils,
            "submitted_at": registration.created_at,
            "approved_by": registration.reviewed_by.email if registration.reviewed_by else "",
            "approved_at": registration.reviewed_at,
        }
        if registration
        else None,
        "owner": {
            "name": owner.get_full_name(),
            "email": owner.email,
            "phone": owner.phone,
            "last_login": owner.last_login,
        }
        if owner
        else None,
        "people": {
            "by_role": [
                {"role": role, "label": Role(role).label, "count": by_role[role]}
                for role in Role.values
                if by_role.get(role)
            ],
            "staff": staff_users.count(),
            "staff_with_app": with_app,
            "not_joined": not_joined,
            "last_sign_in": last_sign_in,
        },
        "lifecycle": {
            "status_reason": tenant.status_reason,
            "status_note": tenant.status_note,
            "status_changed_at": tenant.status_changed_at,
            "purge_after": tenant.purge_after,
            "purged_at": tenant.purged_at,
        },
        "billing": _billing_summary(tenant),
        "usage": _usage_dict(usage),
        "band": band_dict(usage.pupils) if usage else None,
        "attention": attention(tenant, usage, now) if tenant.status == Tenant.Status.ACTIVE else [],
        "history": [
            {
                "day": row.day.isoformat(),
                "pupils": row.pupils,
                "active_users_7d": row.active_users_7d,
                "registers_7d": row.registers_7d,
            }
            for row in history
        ],
        "platform_events": [
            {
                "occurred_at": e.occurred_at,
                "actor_email": e.actor_email,
                "action": e.action,
                "reason": e.reason,
            }
            for e in events
        ],
    }
