"""Payroll rules (Ghana):

- SSNIT: the employee pays ``ssnit_employee_percent`` (5.5%) and the school
  ``ssnit_employer_percent`` (13%) of basic salary, up to the monthly cap.
- PAYE is charged on taxable pay less the employee's SSNIT, using the school's
  confirmed band table (default: GRA's monthly bands from 1 September 2026).
- Net pay = gross - employee SSNIT - PAYE - other deductions.
- Approving a run (the proprietor) posts it to the books:
      Salaries and wages DR gross, Employer SSNIT DR employer share
      PAYE payable CR, SSNIT payable CR (both shares), Other deductions payable CR,
      Net salaries payable CR net
  Paying it moves the net from Net salaries payable to Cash and bank.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.http import HttpRequest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.finance.models import LedgerAccount
from apps.finance.services import CASH, post_entry
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event

from .models import PayrollSettings, PayRun, Payslip, Salary

SALARIES, EMPLOYER_SSNIT = "5100", "5110"
PAYE_PAYABLE, SSNIT_PAYABLE, NET_PAYABLE, OTHER_PAYABLE = "2300", "2310", "2320", "2330"
ACCOUNTS = [
    (SALARIES, "Salaries and wages", LedgerAccount.Type.EXPENSE),
    (EMPLOYER_SSNIT, "Employer SSNIT", LedgerAccount.Type.EXPENSE),
    (PAYE_PAYABLE, "PAYE owed to GRA", LedgerAccount.Type.LIABILITY),
    (SSNIT_PAYABLE, "SSNIT owed", LedgerAccount.Type.LIABILITY),
    (NET_PAYABLE, "Salaries owed to staff", LedgerAccount.Type.LIABILITY),
    (OTHER_PAYABLE, "Other payroll deductions owed", LedgerAccount.Type.LIABILITY),
]


def ensure_accounts() -> None:
    for code, name, kind in ACCOUNTS:
        LedgerAccount.objects.get_or_create(code=code, defaults={"name": name, "type": kind})


def _pct(amount: int, percent: Decimal) -> int:
    return int((Decimal(amount) * percent / 100).quantize(Decimal("1"), ROUND_HALF_UP))


def paye(taxable_pesewas: int, bands: list[list[Any]]) -> int:
    """Tax on a month's chargeable income, band by band."""
    left, tax = max(0, taxable_pesewas), Decimal(0)
    for width, rate in bands:
        portion = left if width is None else min(left, int(width))
        tax += Decimal(portion) * Decimal(str(rate)) / 100
        left -= portion
        if left <= 0:
            break
    return int(tax.quantize(Decimal("1"), ROUND_HALF_UP))


def validate_bands(bands: Any) -> list[list[Any]]:
    if not isinstance(bands, list) or len(bands) < 2:
        raise ValidationError({"paye_bands": "Give at least two bands."})
    clean = []
    for i, band in enumerate(bands):
        try:
            width, rate = band
            rate_value = Decimal(str(rate))
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise ValidationError({"paye_bands": f"Band {i + 1} isn't [width, rate]."}) from exc
        last = i == len(bands) - 1
        if last != (width is None):
            raise ValidationError({"paye_bands": "Only the last band is open-ended."})
        if width is not None and (not isinstance(width, int) or width <= 0):
            raise ValidationError({"paye_bands": f"Band {i + 1} needs a width in pesewas."})
        if not 0 <= rate_value <= 100:
            raise ValidationError({"paye_bands": f"Band {i + 1}'s rate must be 0 to 100."})
        clean.append([width, str(rate_value)])
    return clean


def figures(salary: Salary, settings: PayrollSettings) -> dict[str, Any]:
    basic = salary.basic_pesewas
    allowances = [
        {
            "name": a["name"],
            "amount_pesewas": int(a["amount_pesewas"]),
            "taxable": bool(a.get("taxable", True)),
        }
        for a in salary.allowances or []
    ]
    gross = basic + sum(a["amount_pesewas"] for a in allowances)
    insurable = min(basic, settings.ssnit_cap_pesewas)
    ssnit_employee = _pct(insurable, settings.ssnit_employee_percent)
    ssnit_employer = _pct(insurable, settings.ssnit_employer_percent)
    taxable = basic + sum(a["amount_pesewas"] for a in allowances if a["taxable"]) - ssnit_employee
    tax = paye(taxable, settings.paye_bands)
    deductions = [
        {"name": d["name"], "amount_pesewas": int(d["amount_pesewas"])}
        for d in salary.deductions or []
    ]
    other = sum(d["amount_pesewas"] for d in deductions)
    return {
        "basic_pesewas": basic,
        "allowances": allowances,
        "gross_pesewas": gross,
        "ssnit_employee_pesewas": ssnit_employee,
        "ssnit_employer_pesewas": ssnit_employer,
        "taxable_pesewas": max(0, taxable),
        "paye_pesewas": tax,
        "deductions": deductions,
        "deductions_pesewas": other,
        "net_pesewas": gross - ssnit_employee - tax - other,
    }


def prepare(*, request: HttpRequest, month: dt.date) -> PayRun:
    """Work out (or work out again) a month's pay run while it's still a draft."""
    settings = PayrollSettings.load()
    if settings.rates_confirmed_at is None:
        raise ValidationError(
            {
                "detail": "Confirm the PAYE and SSNIT rates against GRA's table "
                "under Payroll rules first."
            }
        )
    month = month.replace(day=1)
    if month > timezone.localdate().replace(day=1) + dt.timedelta(days=31):
        raise ValidationError({"month": "Prepare at most next month's pay."})
    salaries = list(
        Salary.objects.filter(
            on_payroll=True, staff__is_active=True, basic_pesewas__gt=0
        ).select_related("staff")
    )
    if not salaries:
        raise ValidationError({"detail": "Nobody is on the payroll yet. Set salaries first."})
    with tenant_atomic():
        run, _ = PayRun.objects.get_or_create(
            month=month, defaults={"prepared_by": request.user.pk}
        )
        if run.status != PayRun.Status.DRAFT:
            raise ValidationError({"detail": "This month's pay has already been approved."})
        run.payslips.all().delete()
        slips = []
        for salary in salaries:
            numbers = figures(salary, settings)
            if numbers["net_pesewas"] < 0:
                raise ValidationError(
                    {
                        "detail": f"{salary.staff.first_name} {salary.staff.last_name}'s "
                        "deductions are more than their pay."
                    }
                )
            slips.append(
                Payslip(
                    run=run,
                    staff=salary.staff,
                    staff_name=f"{salary.staff.first_name} {salary.staff.last_name}",
                    **numbers,
                )
            )
        Payslip.objects.bulk_create(slips)
        for field in ("gross", "paye", "ssnit_employee", "ssnit_employer", "net"):
            setattr(run, f"{field}_pesewas", sum(getattr(s, f"{field}_pesewas") for s in slips))
        run.other_deductions_pesewas = sum(s.deductions_pesewas for s in slips)
        run.prepared_by = request.user.pk
        run.save()
        record_event(
            action="payroll.prepared", request=request, target=run, after={"staff": len(slips)}
        )
    return run


def approve(*, request: HttpRequest, run: PayRun) -> PayRun:
    if run.status != PayRun.Status.DRAFT:
        raise ValidationError({"detail": "Only a run being prepared can be approved."})
    ensure_accounts()
    ssnit_total = run.ssnit_employee_pesewas + run.ssnit_employer_pesewas
    with tenant_atomic():
        post_entry(
            memo=f"Payroll {run.month:%B %Y}",
            source_type="payroll",
            source_id=str(run.pk),
            created_by=request.user.pk,
            lines=[
                (SALARIES, run.gross_pesewas, 0),
                (EMPLOYER_SSNIT, run.ssnit_employer_pesewas, 0),
                (PAYE_PAYABLE, 0, run.paye_pesewas),
                (SSNIT_PAYABLE, 0, ssnit_total),
                (OTHER_PAYABLE, 0, run.other_deductions_pesewas),
                (NET_PAYABLE, 0, run.net_pesewas),
            ],
        )
        run.status, run.approved_by, run.approved_at = (
            PayRun.Status.APPROVED,
            request.user.pk,
            timezone.now(),
        )
        run.save(update_fields=["status", "approved_by", "approved_at"])
        record_event(
            action="payroll.approved",
            request=request,
            target=run,
            after={"net_pesewas": run.net_pesewas},
        )
    return run


def mark_paid(*, request: HttpRequest, run: PayRun) -> PayRun:
    from apps.communication.services import notify_users

    if run.status != PayRun.Status.APPROVED:
        raise ValidationError({"detail": "Approve the run before paying it."})
    with tenant_atomic():
        post_entry(
            memo=f"Salaries paid {run.month:%B %Y}",
            source_type="payroll_paid",
            source_id=str(run.pk),
            created_by=request.user.pk,
            lines=[(NET_PAYABLE, run.net_pesewas, 0), (CASH, 0, run.net_pesewas)],
        )
        run.status, run.paid_at = PayRun.Status.PAID, timezone.now()
        run.save(update_fields=["status", "paid_at"])
        record_event(action="payroll.paid", request=request, target=run)
    staff_users = [s.staff.user_id for s in run.payslips.select_related("staff") if s.staff.user_id]
    notify_users(
        staff_users,
        kind="payslip",
        title=f"Your payslip for {run.month:%B %Y}",
        body="Your pay has been paid. Open Payroll in Nex Edu to see your payslip.",
        data={"run": str(run.pk)},
    )
    return run


def require_own_or_manager(request: HttpRequest, slip: Payslip, *, manage: bool) -> None:
    if manage:
        return
    if slip.staff.user_id != request.user.pk:
        raise PermissionDenied("You can only see your own payslips.")
    if slip.run.status == PayRun.Status.DRAFT:
        raise PermissionDenied("This payslip isn't final yet.")


def schedule_csv(run: PayRun, kind: str) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    salaries = {
        s.staff_id: s for s in Salary.objects.filter(staff__in=run.payslips.values("staff"))
    }
    cedi = lambda p: f"{p / 100:.2f}"  # noqa: E731
    if kind == "paye":
        writer.writerow(["Name", "TIN", "Taxable pay (GHS)", "PAYE (GHS)"])
        for s in run.payslips.all():
            sal = salaries.get(s.staff_id)
            writer.writerow(
                [
                    s.staff_name,
                    sal.tin if sal else "",
                    cedi(s.taxable_pesewas),
                    cedi(s.paye_pesewas),
                ]
            )
    else:
        writer.writerow(
            [
                "Name",
                "SSNIT number",
                "Basic salary (GHS)",
                "Employee 5.5% (GHS)",
                "Employer 13% (GHS)",
                "Total (GHS)",
            ]
        )
        for s in run.payslips.all():
            sal = salaries.get(s.staff_id)
            writer.writerow(
                [
                    s.staff_name,
                    sal.ssnit_number if sal else "",
                    cedi(s.basic_pesewas),
                    cedi(s.ssnit_employee_pesewas),
                    cedi(s.ssnit_employer_pesewas),
                    cedi(s.ssnit_employee_pesewas + s.ssnit_employer_pesewas),
                ]
            )
    return out.getvalue()


def payslip_pdf(slip: Payslip) -> bytes:
    from xml.sax.saxutils import escape

    from apps.school.models import SchoolProfile
    from core import pdf

    profile = SchoolProfile.load()
    cedi = lambda p: f"GH₵{p / 100:,.2f}"  # noqa: E731

    def build(width: float) -> list[Any]:
        story = pdf.header(profile, f"Payslip, {slip.run.month:%B %Y}")
        story.append(
            pdf.key_values(
                [("Name", escape(slip.staff_name)), ("Staff no.", escape(slip.staff.staff_number))],
                width,
            )
        )
        rows: list[list[Any]] = [["", "GH₵"], ["Basic salary", cedi(slip.basic_pesewas)]]
        rows += [[escape(a["name"]), cedi(a["amount_pesewas"])] for a in slip.allowances]
        rows += [
            ["Gross pay", cedi(slip.gross_pesewas)],
            ["SSNIT (5.5%)", f"-{cedi(slip.ssnit_employee_pesewas)}"],
        ]
        rows += [["PAYE", f"-{cedi(slip.paye_pesewas)}"]]
        rows += [[escape(d["name"]), f"-{cedi(d['amount_pesewas'])}"] for d in slip.deductions]
        rows += [["Net pay", cedi(slip.net_pesewas)]]
        story.append(pdf.table(rows, [width * 0.7, width * 0.3], align_right_from=1))
        return story

    return pdf.render(build, title=f"Payslip {slip.staff_name}", footer=f"{slip.run.month:%B %Y}")
