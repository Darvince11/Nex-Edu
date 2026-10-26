"""Finance reports for school leaders and the bursar: who still owes, and what was
collected (by day, method and class). Money in pesewas throughout."""

from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any

from django.db.models import Count, Max, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.academics.models import Term
from apps.students.models import StudentGuardian

from .models import Invoice, Payment


def balances(term: Term, arm: str | None = None, minimum: int = 1) -> dict[str, Any]:
    """Pupils who still owe for the term, largest balance first."""
    invoices = (
        Invoice.objects.filter(term=term)
        .exclude(status=Invoice.Status.VOID)
        .select_related("student__arm__level")
    )
    if arm:
        invoices = invoices.filter(student__arm_id=arm)
    last_paid = dict(
        Payment.objects.filter(invoice__term=term, status=Payment.Status.SUCCESS)
        .values("invoice_id")
        .annotate(last=Max("paid_at"))
        .values_list("invoice_id", "last")
    )
    contacts: dict[Any, str] = {}
    for g in StudentGuardian.objects.filter(student__invoices__term=term).order_by("-is_primary"):
        contacts.setdefault(g.student_id, g.phone)
    rows = []
    for inv in invoices:
        balance = inv.balance_pesewas
        if balance < minimum:
            continue
        rows.append(
            {
                "invoice": inv.number,
                "student": str(inv.student_id),
                "name": inv.student.full_name,
                "admission_number": inv.student.admission_number,
                "class": str(inv.student.arm) if inv.student.arm_id else "",
                "billed_pesewas": inv.total_pesewas,
                "paid_pesewas": inv.paid_pesewas,
                "balance_pesewas": balance,
                "guardian_phone": contacts.get(inv.student_id, ""),
                "last_payment": last_paid.get(inv.pk),
                "due_date": inv.due_date,
            }
        )
    rows.sort(key=lambda r: -r["balance_pesewas"])
    return {
        "term": term.pk,
        "pupils": len(rows),
        "outstanding_pesewas": sum(r["balance_pesewas"] for r in rows),
        "rows": rows,
    }


def balances_csv(report: dict[str, Any]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "Pupil",
            "Admission no.",
            "Class",
            "Billed (GHS)",
            "Paid (GHS)",
            "Owes (GHS)",
            "Guardian phone",
            "Last payment",
        ]
    )
    for r in report["rows"]:
        writer.writerow(
            [
                r["name"],
                r["admission_number"],
                r["class"],
                f"{r['billed_pesewas'] / 100:.2f}",
                f"{r['paid_pesewas'] / 100:.2f}",
                f"{r['balance_pesewas'] / 100:.2f}",
                r["guardian_phone"],
                r["last_payment"].date().isoformat() if r["last_payment"] else "",
            ]
        )
    return out.getvalue()


def _class_label(level: str | None, arm: str | None) -> str:
    return f"{level} {arm}" if level else "No class"


def collections(start: dt.date, end: dt.date) -> dict[str, Any]:
    """Money received between two dates: totals, by day, by method and by class."""
    paid = Payment.objects.filter(
        status=Payment.Status.SUCCESS, paid_at__date__gte=start, paid_at__date__lte=end
    )
    totals = paid.aggregate(total=Sum("amount_received_pesewas"), n=Count("pk"))
    by_day = {
        row["day"]: row
        for row in paid.annotate(day=TruncDate("paid_at", tzinfo=timezone.get_current_timezone()))
        .values("day")
        .annotate(total=Sum("amount_received_pesewas"), n=Count("pk"))
    }
    days, day = [], start
    while day <= end:
        row = by_day.get(day, {})
        days.append(
            {
                "day": day.isoformat(),
                "total_pesewas": row.get("total") or 0,
                "payments": row.get("n") or 0,
            }
        )
        day += dt.timedelta(days=1)
    methods = [
        {"method": row["method"], "total_pesewas": row["total"] or 0, "payments": row["n"]}
        for row in paid.values("method")
        .annotate(total=Sum("amount_received_pesewas"), n=Count("pk"))
        .order_by("-total")
    ]
    classes = [
        {
            "class": _class_label(
                row["invoice__student__arm__level__name"], row["invoice__student__arm__name"]
            ),
            "total_pesewas": row["total"] or 0,
            "payments": row["n"],
        }
        for row in paid.values(
            "invoice__student__arm__level__name",
            "invoice__student__arm__name",
            "invoice__student__arm__level__order",
        )
        .annotate(total=Sum("amount_received_pesewas"), n=Count("pk"))
        .order_by("invoice__student__arm__level__order", "invoice__student__arm__name")
    ]
    return {
        "start": start,
        "end": end,
        "total_pesewas": totals["total"] or 0,
        "payments": totals["n"],
        "by_day": days,
        "by_method": methods,
        "by_class": classes,
    }
