"""Nightly anonymised export for the analytics warehouse (Athena over S3).

One JSON line per active school per day, under
``analytics/schools/date=YYYY-MM-DD/part-0.jsonl`` (Hive-style partitions Athena
reads directly). Aggregates only: no pupil, parent or staff appears in any form.
Schools are identified by a keyed hash, not their name or address, so the
warehouse can follow a school over time without saying which school it is.
Breakdowns are left out when a group has fewer than ``MIN_GROUP`` pupils, so a
small class can't be singled out.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from control_plane.models import SchoolRegistration, Tenant
from control_plane.tenancy import tenant_context

logger = logging.getLogger(__name__)

MIN_GROUP = 10


def school_key(tenant: Tenant) -> str:
    secret = hashlib.sha256(f"analytics:{settings.SECRET_KEY}".encode()).digest()
    return hmac.new(secret, str(tenant.pk).encode(), hashlib.sha256).hexdigest()[:24]


def _rate(part: Any, whole: Any) -> float | None:
    return round(float(part) / float(whole), 4) if whole else None


def school_row(tenant: Tenant, day: dt.date) -> dict[str, Any]:
    from apps.academics.models import Term
    from apps.assessments.models import ReportCard
    from apps.attendance.models import AttendanceRecord
    from apps.finance.models import Invoice
    from apps.students.models import Student
    from control_plane.modules import active_modules
    from control_plane.pricing import band_for
    from control_plane.usage import latest_usage

    registration = SchoolRegistration.objects.filter(tenant=tenant).first()
    usage = latest_usage([tenant]).get(tenant.pk)
    with tenant_context(tenant):
        active = Student.objects.filter(status=Student.Status.ACTIVE)
        pupils = active.count()
        by_level = {
            row["arm__level__name"]: row["n"]
            for row in active.values("arm__level__name").annotate(n=Count("pk"))
            if row["arm__level__name"]
        }
        marks = AttendanceRecord.objects.filter(date__gt=day - dt.timedelta(days=30), date__lte=day)
        counted = marks.aggregate(
            total=Count("pk"), present=Count("pk", filter=Q(status__in=["present", "late"]))
        )
        term = Term.objects.filter(is_current=True).first()
        cards = ReportCard.objects.filter(term=term) if term else ReportCard.objects.none()
        published = cards.filter(status=ReportCard.Status.PUBLISHED)
        average = published.aggregate(a=Avg("average"))["a"]
        published_count = published.count()
        owed = (
            Invoice.objects.filter(term=term)
            .exclude(status=Invoice.Status.VOID)
            .aggregate(billed=Sum("total_pesewas"), paid=Sum("paid_pesewas"))
            if term
            else {"billed": 0, "paid": 0}
        )
    return {
        "school": school_key(tenant),
        "date": day.isoformat(),
        "region": registration.region if registration else "",
        "school_type": registration.school_type if registration else "",
        "price_band": band_for(pupils).code,
        "pupils": pupils,
        "pupils_by_level": by_level if all(n >= MIN_GROUP for n in by_level.values()) else None,
        "attendance_rate_30d": _rate(counted["present"], counted["total"]),
        "report_cards_published": published_count,
        "average_score_term": float(Decimal(average).quantize(Decimal("0.1")))
        if average is not None and published_count >= MIN_GROUP
        else None,
        "fee_collection_rate_term": _rate(owed["paid"] or 0, owed["billed"] or 0),
        "active_users_7d": usage.active_users_7d if usage else None,
        "modules": sorted(active_modules(tenant)),
    }


def export_day(day: dt.date | None = None) -> str:
    """Write one day's file (replacing it if run again). Returns the storage key."""
    day = day or timezone.localdate() - dt.timedelta(days=1)
    rows = []
    for tenant in Tenant.objects.filter(status=Tenant.Status.ACTIVE).order_by("pk"):
        try:
            rows.append(school_row(tenant, day))
        except Exception:
            logger.exception("Analytics row failed for %s", tenant.slug)
    key = f"{settings.ANALYTICS_PREFIX}schools/date={day.isoformat()}/part-0.jsonl"
    body = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    if default_storage.exists(key):
        default_storage.delete(key)
    return default_storage.save(key, ContentFile(body.encode()))
