"""Dashboard figures, built only from what the viewer may already see.

Every figure starts from visible_students() (whole school for leaders, own
classes for teachers, own children for parents), so a chart never reveals more
than the pages behind it. Sections the viewer has no permission for are left out.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncWeek
from django.utils import timezone

from apps.academics.models import Term
from apps.assessments.models import ReportCard
from apps.attendance.models import AttendanceRecord
from apps.finance.models import Invoice, Payment
from apps.students.models import Student
from apps.students.selectors import visible_students
from core.rbac import STAFF_ROLES, Perm

ATTENDANCE_DAYS = 20  # school days shown on the trend
ONE = Decimal("0.1")


def _pct(part: int, whole: int) -> float | None:
    if not whole:
        return None
    return float((Decimal(part) * 100 / whole).quantize(ONE, ROUND_HALF_UP))


def enrolment(students: Any) -> list[dict[str, Any]]:
    """Active pupils per class, in school order."""
    rows = (
        students.filter(status=Student.Status.ACTIVE, arm__isnull=False)
        .values("arm_id", "arm__level__name", "arm__name", "arm__level__order")
        .annotate(
            pupils=Count("pk", distinct=True),
            girls=Count("pk", filter=Q(gender="female"), distinct=True),
        )
        .order_by("arm__level__order", "arm__name")
    )
    return [
        {
            "arm": str(r["arm_id"]),
            "label": f"{r['arm__level__name']} {r['arm__name']}",
            "pupils": r["pupils"],
            "girls": r["girls"],
            "boys": r["pupils"] - r["girls"],
        }
        for r in rows
    ]


def attendance_trend(students: Any, arm: str | None = None) -> list[dict[str, Any]]:
    """Daily register totals for the most recent school days with a register."""
    records = AttendanceRecord.objects.filter(student__in=students)
    if arm:
        records = records.filter(arm_id=arm)
    dates = list(
        records.order_by("-date").values_list("date", flat=True).distinct()[:ATTENDANCE_DAYS]
    )
    if not dates:
        return []
    S = AttendanceRecord.Status
    rows = (
        records.filter(date__in=dates)
        .values("date")
        .annotate(
            present=Count("pk", filter=Q(status=S.PRESENT)),
            late=Count("pk", filter=Q(status=S.LATE)),
            absent=Count("pk", filter=Q(status=S.ABSENT)),
            excused=Count("pk", filter=Q(status=S.EXCUSED)),
            marked=Count("pk"),
        )
        .order_by("date")
    )
    return [
        {
            "date": r["date"].isoformat(),
            "present": r["present"],
            "late": r["late"],
            "absent": r["absent"],
            "excused": r["excused"],
            "marked": r["marked"],
            # Late still counts as in school, as on the report card.
            "rate": _pct(r["present"] + r["late"], r["marked"]),
        }
        for r in rows
    ]


def fees(term: Term) -> dict[str, Any]:
    """Billed, collected and owed this term, by class and by week collected."""
    live = Invoice.objects.filter(term=term).exclude(status=Invoice.Status.VOID)
    totals = live.aggregate(billed=Sum("total_pesewas"), collected=Sum("paid_pesewas"))
    billed, collected = totals["billed"] or 0, totals["collected"] or 0
    by_class = (
        live.values("student__arm__level__name", "student__arm__name", "student__arm__level__order")
        .annotate(billed=Sum("total_pesewas"), collected=Sum("paid_pesewas"))
        .order_by("student__arm__level__order", "student__arm__name")
    )
    weekly = (
        Payment.objects.filter(
            invoice__term=term, status=Payment.Status.SUCCESS, paid_at__isnull=False
        )
        .annotate(week=TruncWeek("paid_at", tzinfo=timezone.get_current_timezone()))
        .values("week")
        .annotate(amount=Sum("amount_received_pesewas"), payments=Count("pk"))
        .order_by("week")
    )
    return {
        "billed_pesewas": billed,
        "collected_pesewas": collected,
        "outstanding_pesewas": billed - collected,
        "collection_rate": _pct(collected, billed),
        "by_class": [
            {
                "label": (
                    f"{r['student__arm__level__name']} {r['student__arm__name']}"
                    if r["student__arm__level__name"]
                    else "No class"
                ),
                "billed_pesewas": r["billed"] or 0,
                "collected_pesewas": r["collected"] or 0,
                "outstanding_pesewas": (r["billed"] or 0) - (r["collected"] or 0),
            }
            for r in by_class
        ],
        "weekly": [
            {
                "week": (
                    r["week"].date() if isinstance(r["week"], dt.datetime) else r["week"]
                ).isoformat(),
                "amount_pesewas": r["amount"] or 0,
                "payments": r["payments"],
            }
            for r in weekly
        ],
    }


def results(cards: Any) -> dict[str, Any]:
    """Average total per subject and how many of each grade, from report cards."""
    totals: dict[str, list[Decimal]] = defaultdict(list)
    names: dict[str, str] = {}
    grades: Counter[str] = Counter()
    points: dict[str, int] = {}
    count = 0
    for lines in cards.values_list("lines", flat=True):
        count += 1
        for line in lines:
            code = line.get("code") or line.get("subject", "")
            names[code] = line.get("subject", code)
            totals[code].append(Decimal(line.get("total") or 0))
            if grade := line.get("grade"):
                grades[grade] += 1
                if line.get("points") is not None:
                    points.setdefault(grade, line["points"])
    subjects = sorted(
        (
            {
                "code": code,
                "subject": names[code],
                "average": float(
                    (sum(values, Decimal(0)) / len(values)).quantize(ONE, ROUND_HALF_UP)
                ),
                "pupils": len(values),
            }
            for code, values in totals.items()
        ),
        key=lambda s: s["subject"],
    )
    return {
        "report_cards": count,
        "subjects": subjects,
        "grades": [
            {"grade": g, "count": grades[g]}
            for g in sorted(grades, key=lambda g: (points.get(g, 99), g))
        ],
    }


def insights(
    *,
    user: Any,
    roles: frozenset[str],
    permissions: frozenset[str],
    term: Term | None,
    arm: str | None,
) -> dict[str, Any]:
    students = visible_students(user, roles, permissions)
    staff = bool(roles & STAFF_ROLES)
    out: dict[str, Any] = {"term": term.pk if term else None, "generated_at": timezone.now()}
    if staff and Perm.STUDENTS_VIEW in permissions:
        out["enrolment"] = enrolment(students)
    if Perm.ATTENDANCE_VIEW in permissions or not staff:
        out["attendance"] = attendance_trend(students, arm)
    # Parents hold finance.view for their own invoices only; school totals are staff-only.
    from control_plane.modules import is_active
    from control_plane.tenancy import require_tenant

    if term and staff and Perm.FINANCE_VIEW in permissions and is_active(require_tenant(), "fees"):
        out["fees"] = fees(term)
    if term and (Perm.ASSESSMENTS_VIEW in permissions or not staff):
        cards = ReportCard.objects.filter(term=term, student__in=students)
        if not staff:
            cards = cards.filter(status=ReportCard.Status.PUBLISHED)
        if arm:
            cards = cards.filter(arm_id=arm)
        out["results"] = results(cards)
    return out
