"""Subscription pricing and payments from schools to Nex Edu.

Price changes need a reason and land in the platform audit log with the old
and new amounts. Payments are recorded by platform staff as schools pay (mobile
money, bank transfer, ...); automatic invoicing comes later.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from control_plane.audit import record_platform_event
from control_plane.models import BillingSettings, PriceBandSetting, SubscriptionPayment, Tenant
from control_plane.pricing import band_for, price_bands
from control_plane.usage import latest_usage


@transaction.atomic
def update_band(*, request: Any, code: str, price_pesewas: int, reason: str) -> PriceBandSetting:
    if not reason.strip():
        raise ValidationError({"reason": "Say why the price is changing."})
    band = PriceBandSetting.objects.select_for_update().get(code=code)
    before = band.price_pesewas
    if before == price_pesewas:
        return band
    band.price_pesewas = price_pesewas
    band.save(update_fields=["price_pesewas", "updated_at"])
    record_platform_event(
        action="billing.price_changed",
        request=request,
        target=band,
        data={"band": band.code, "before_pesewas": before, "after_pesewas": price_pesewas},
        reason=reason.strip(),
    )
    return band


@transaction.atomic
def set_period(*, request: Any, period: str) -> BillingSettings:
    settings = BillingSettings.load()
    if settings.period != period:
        before = settings.period
        settings.period = period
        settings.save(update_fields=["period", "updated_at"])
        record_platform_event(
            action="billing.period_changed",
            request=request,
            target=settings,
            data={"before": before, "after": period},
        )
    return settings


@transaction.atomic
def record_payment(*, request: Any, tenant: Tenant, **data: Any) -> SubscriptionPayment:
    if data["received_on"] > timezone.localdate():
        raise ValidationError({"received_on": "A payment can't be received in the future."})
    usage = latest_usage([tenant]).get(tenant.pk)
    payment = SubscriptionPayment.objects.create(
        tenant=tenant,
        recorded_by=request.user,
        band_code=band_for(usage.pupils).code if usage else "",
        pupils=usage.pupils if usage else None,
        **data,
    )
    record_platform_event(
        action="billing.payment_recorded",
        request=request,
        tenant=tenant,
        target=payment,
        data={
            "amount_pesewas": payment.amount_pesewas,
            "period": payment.period_label,
            "method": payment.method,
        },
    )
    return payment


def pricing_overview() -> dict[str, Any]:
    """Bands with how many schools sit in each and what they'd pay."""
    bands = price_bands()
    active = list(Tenant.objects.filter(status=Tenant.Status.ACTIVE).order_by("name"))
    latest = latest_usage(active)
    schools = []
    for tenant in active:
        usage = latest.get(tenant.pk)
        band = band_for(usage.pupils, bands) if usage else None
        schools.append(
            {
                "slug": tenant.slug,
                "name": tenant.name,
                "pupils": usage.pupils if usage else None,
                "band_code": band.code if band else None,
                "amount_pesewas": band.price_pesewas if band else None,
            }
        )
    settings = BillingSettings.load()
    return {
        "period": settings.period,
        "period_label": settings.get_period_display(),
        "free_trial_days": 0,
        "bands": [
            {
                "code": b.code,
                "label": b.label,
                "max_pupils": b.max_pupils,
                "price_pesewas": b.price_pesewas,
                "schools": sum(1 for s in schools if s["band_code"] == b.code),
            }
            for b in bands
        ],
        "schools": schools,
        "expected_pesewas": sum(s["amount_pesewas"] or 0 for s in schools),
    }


def history(*, school: str | None = None, before_month: bool = False) -> dict[str, Any]:
    """Payments, newest first, with monthly totals for the chart. ``before_month``
    keeps only payments received before the current month."""
    payments = SubscriptionPayment.objects.select_related("tenant", "recorded_by")
    if school:
        payments = payments.filter(tenant__slug=school)
    month_start = timezone.localdate().replace(day=1)
    if before_month:
        payments = payments.filter(received_on__lt=month_start)
    year_ago = (month_start - dt.timedelta(days=335)).replace(day=1)
    by_month = {
        (row["month"].date() if isinstance(row["month"], dt.datetime) else row["month"]): row
        for row in payments.filter(received_on__gte=year_ago)
        .annotate(month=TruncMonth("received_on"))
        .values("month")
        .annotate(total=Sum("amount_pesewas"), n=Count("pk"))
    }
    months, month = [], year_ago
    while month <= month_start:
        row = by_month.get(month, {})
        months.append(
            {
                "month": month.isoformat(),
                "total_pesewas": row.get("total") or 0,
                "payments": row.get("n") or 0,
            }
        )
        month = (month + dt.timedelta(days=32)).replace(day=1)
    totals = payments.aggregate(total=Sum("amount_pesewas"), n=Count("pk"))
    this_month = SubscriptionPayment.objects.filter(received_on__gte=month_start)
    if school:
        this_month = this_month.filter(tenant__slug=school)
    return {
        "total_pesewas": totals["total"] or 0,
        "payments_count": totals["n"],
        "this_month_pesewas": this_month.aggregate(t=Sum("amount_pesewas"))["t"] or 0,
        "before_this_month_pesewas": SubscriptionPayment.objects.filter(
            received_on__lt=month_start, **({"tenant__slug": school} if school else {})
        ).aggregate(t=Sum("amount_pesewas"))["t"]
        or 0,
        "by_month": months,
        "payments": [
            {
                "id": p.pk,
                "school": p.tenant.name,
                "slug": p.tenant.slug,
                "amount_pesewas": p.amount_pesewas,
                "period_label": p.period_label,
                "method": p.method,
                "method_label": p.get_method_display(),
                "reference": p.reference,
                "received_on": p.received_on,
                "band_code": p.band_code,
                "pupils": p.pupils,
                "note": p.note,
                "recorded_by": p.recorded_by.email,
            }
            for p in payments[:500]
        ],
    }
