"""Spending, other income, budgets and the reports a school's accounts need.

- Money spent:     <expense account> DR  /  Cash and bank  CR
- Money received:  Cash and bank      DR  /  <income account> CR
- Voiding posts the exact reverse, dated today; the original stays in the books.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db.models import Q, Sum
from django.http import HttpRequest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.academics.models import AcademicSession
from apps.finance.models import JournalLine, LedgerAccount
from apps.finance.services import CASH, post_entry, seed_ledger_accounts
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event

from .models import Budget, Transaction

T = LedgerAccount.Type
DEFAULT_ACCOUNTS = [
    ("5100", "Salaries and wages", T.EXPENSE),
    ("5200", "Utilities (electricity, water, internet)", T.EXPENSE),
    ("5300", "Teaching and learning materials", T.EXPENSE),
    ("5400", "Repairs and maintenance", T.EXPENSE),
    ("5500", "Transport and fuel", T.EXPENSE),
    ("5600", "Feeding and kitchen", T.EXPENSE),
    ("5700", "Stationery and printing", T.EXPENSE),
    ("5800", "Bank and mobile money charges", T.EXPENSE),
    ("5900", "Other expenses", T.EXPENSE),
    ("4200", "Donations and grants", T.INCOME),
    ("4300", "Other income", T.INCOME),
]
RANGES = {T.EXPENSE: (5000, 5999), T.INCOME: (4000, 4999)}
MAX_AMOUNT = 1_000_000_000_00  # GH₵1bn


def ensure_accounts() -> None:
    seed_ledger_accounts()
    for code, name, kind in DEFAULT_ACCOUNTS:
        LedgerAccount.objects.get_or_create(code=code, defaults={"name": name, "type": kind})


def add_account(*, name: str, kind: str) -> LedgerAccount:
    if kind not in RANGES:
        raise ValidationError({"type": "Add an expense or an income account."})
    low, high = RANGES[kind]
    if LedgerAccount.objects.filter(name__iexact=name.strip()).exists():
        raise ValidationError({"name": "There's already an account with this name."})
    used = {int(c) for c in LedgerAccount.objects.values_list("code", flat=True) if c.isdigit()}
    code = next((c for c in range(low + 10, high + 1, 10) if c not in used), None)
    if code is None:
        raise ValidationError({"name": "No account numbers left in this range."})
    return LedgerAccount.objects.create(code=str(code), name=name.strip(), type=kind)


def _posted_at(day: dt.date) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, dt.time(12, 0)))


def record(
    *,
    request: HttpRequest,
    kind: str,
    date: dt.date,
    account: LedgerAccount,
    amount: int,
    method: str,
    party: str,
    reference: str = "",
    description: str = "",
) -> Transaction:
    wanted = T.EXPENSE if kind == Transaction.Kind.EXPENSE else T.INCOME
    if account.type != wanted:
        raise ValidationError({"account": f"Choose an {wanted} account."})
    if not 0 < amount <= MAX_AMOUNT:
        raise ValidationError({"amount_pesewas": "Enter the amount."})
    if date > timezone.localdate():
        raise ValidationError({"date": "It can't be in the future."})
    ensure_accounts()
    lines = (
        [(account.code, amount, 0), (CASH, 0, amount)]
        if kind == Transaction.Kind.EXPENSE
        else [(CASH, amount, 0), (account.code, 0, amount)]
    )
    with tenant_atomic():
        entry = post_entry(
            memo=f"{account.name}: {party}",
            source_type=f"accounting_{kind}",
            source_id=reference or party,
            created_by=request.user.pk,
            lines=lines,
            posted_at=_posted_at(date),
        )
        txn = Transaction.objects.create(
            kind=kind,
            date=date,
            account=account,
            amount_pesewas=amount,
            method=method,
            party=party.strip(),
            reference=reference.strip(),
            description=description.strip(),
            entry=entry,
            recorded_by=request.user.pk,
        )
        record_event(
            action=f"accounting.{kind}",
            request=request,
            target=txn,
            after={"account": account.name, "amount_pesewas": amount, "party": party},
        )
    return txn


def void(*, request: HttpRequest, txn: Transaction, reason: str) -> Transaction:
    if txn.voided_by_entry_id:
        raise ValidationError({"detail": "Already voided."})
    if not reason.strip():
        raise ValidationError({"reason": "Say why it's being voided."})
    original = list(txn.entry.lines.select_related("account"))
    with tenant_atomic():
        reversal = post_entry(
            memo=f"Void: {txn.entry.memo}"[:200],
            source_type="reversal",
            source_id=str(txn.pk),
            created_by=request.user.pk,
            reverses=txn.entry,
            lines=[
                (line.account.code, line.credit_pesewas, line.debit_pesewas) for line in original
            ],
        )
        txn.voided_by_entry = reversal
        txn.void_reason = reason.strip()
        txn.save(update_fields=["voided_by_entry", "void_reason"])
        record_event(action="accounting.voided", request=request, target=txn, reason=reason)
    return txn


def _lines(start: dt.date | None = None, end: dt.date | None = None) -> Any:
    lines = JournalLine.objects.all()
    if start:
        lines = lines.filter(entry__posted_at__date__gte=start)
    if end:
        lines = lines.filter(entry__posted_at__date__lte=end)
    return lines


def trial_balance(as_of: dt.date) -> dict[str, Any]:
    rows = (
        _lines(end=as_of)
        .values("account__code", "account__name", "account__type")
        .annotate(d=Sum("debit_pesewas"), c=Sum("credit_pesewas"))
        .order_by("account__code")
    )
    out = []
    for r in rows:
        balance = (r["d"] or 0) - (r["c"] or 0)
        out.append(
            {
                "code": r["account__code"],
                "name": r["account__name"],
                "type": r["account__type"],
                "debit_pesewas": balance if balance > 0 else 0,
                "credit_pesewas": -balance if balance < 0 else 0,
            }
        )
    return {
        "as_of": as_of,
        "rows": out,
        "debit_total_pesewas": sum(r["debit_pesewas"] for r in out),
        "credit_total_pesewas": sum(r["credit_pesewas"] for r in out),
    }


def income_and_expenditure(start: dt.date, end: dt.date) -> dict[str, Any]:
    rows = (
        _lines(start, end)
        .filter(account__type__in=[T.INCOME, T.EXPENSE])
        .values("account__code", "account__name", "account__type")
        .annotate(d=Sum("debit_pesewas"), c=Sum("credit_pesewas"))
        .order_by("account__code")
    )
    income, spending = [], []
    for r in rows:
        if r["account__type"] == T.INCOME:
            income.append(
                {
                    "code": r["account__code"],
                    "name": r["account__name"],
                    "amount_pesewas": (r["c"] or 0) - (r["d"] or 0),
                }
            )
        else:
            spending.append(
                {
                    "code": r["account__code"],
                    "name": r["account__name"],
                    "amount_pesewas": (r["d"] or 0) - (r["c"] or 0),
                }
            )
    total_in = sum(r["amount_pesewas"] for r in income)
    total_out = sum(r["amount_pesewas"] for r in spending)
    return {
        "start": start,
        "end": end,
        "income": income,
        "expenditure": spending,
        "income_total_pesewas": total_in,
        "expenditure_total_pesewas": total_out,
        "surplus_pesewas": total_in - total_out,
    }


def budget_vs_actual(session: AcademicSession) -> dict[str, Any]:
    budgets = {b.account_id: b.amount_pesewas for b in Budget.objects.filter(session=session)}
    actual = {
        r["account_id"]: (r["d"] or 0) - (r["c"] or 0)
        for r in _lines(session.starts_on, session.ends_on)
        .filter(account__type=T.EXPENSE)
        .values("account_id")
        .annotate(d=Sum("debit_pesewas"), c=Sum("credit_pesewas"))
    }
    accounts = LedgerAccount.objects.filter(Q(pk__in=budgets) | Q(pk__in=actual)).order_by("code")
    rows = []
    for a in accounts:
        planned, spent = budgets.get(a.pk, 0), actual.get(a.pk, 0)
        rows.append(
            {
                "account": a.pk,
                "code": a.code,
                "name": a.name,
                "budget_pesewas": planned,
                "actual_pesewas": spent,
                "left_pesewas": planned - spent,
                "used_percent": round(100 * spent / planned, 1) if planned else None,
            }
        )
    return {"session": session.pk, "session_name": session.name, "rows": rows}


def cash_book(start: dt.date, end: dt.date) -> dict[str, Any]:
    before = (
        _lines(end=start - dt.timedelta(days=1))
        .filter(account__code=CASH)
        .aggregate(d=Sum("debit_pesewas"), c=Sum("credit_pesewas"))
    )
    balance = (before["d"] or 0) - (before["c"] or 0)
    opening = balance
    rows = []
    for line in (
        _lines(start, end)
        .filter(account__code=CASH)
        .select_related("entry")
        .order_by("entry__posted_at", "pk")
    ):
        balance += line.debit_pesewas - line.credit_pesewas
        rows.append(
            {
                "date": timezone.localtime(line.entry.posted_at).date(),
                "memo": line.entry.memo,
                "in_pesewas": line.debit_pesewas,
                "out_pesewas": line.credit_pesewas,
                "balance_pesewas": balance,
            }
        )
    return {
        "start": start,
        "end": end,
        "opening_pesewas": opening,
        "closing_pesewas": balance,
        "rows": rows,
    }
