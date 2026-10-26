"""Canteen money. Rules:

- A pupil's wallet never goes below zero, and never past the day's spending limit.
- Cash top-ups:   Cash and bank      DR   /  Canteen wallets (liability)  CR
- Purchases:      Canteen wallets    DR   /  Canteen sales (income)       CR
- Refunds:        Canteen wallets    DR   /  Cash and bank                CR
- Pupils on a term meal plan are served once a day at no charge.
- Parents are told once when a purchase takes the balance below the low mark.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.http import HttpRequest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.academics.services import current_term
from apps.finance.models import LedgerAccount
from apps.finance.services import CASH, post_entry
from apps.students.models import Student
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event

from .models import MealPlan, MenuItem, Serving, Wallet, WalletEntry

WALLETS, SALES = "2200", "4100"
MAX_TOP_UP = 100_000_00  # GH₵100,000 in one go is surely a typo


def ensure_accounts() -> None:
    for code, name, kind in (
        (WALLETS, "Canteen wallets", LedgerAccount.Type.LIABILITY),
        (SALES, "Canteen sales", LedgerAccount.Type.INCOME),
    ):
        LedgerAccount.objects.get_or_create(code=code, defaults={"name": name, "type": kind})


def wallet_for(student: Student) -> Wallet:
    wallet, _ = Wallet.objects.get_or_create(student=student)
    return wallet


def _locked(student: Student) -> Wallet:
    wallet_for(student)
    return Wallet.objects.select_for_update().get(student=student)


def _move(
    *,
    request: HttpRequest,
    wallet: Wallet,
    kind: str,
    amount: int,
    lines: list[tuple[str, int, int]],
    items: list[dict[str, Any]] | None = None,
    reference: str = "",
) -> WalletEntry:
    ensure_accounts()
    wallet.balance_pesewas += amount
    wallet.save(update_fields=["balance_pesewas", "updated_at"])
    entry = WalletEntry.objects.create(
        wallet=wallet,
        kind=kind,
        amount_pesewas=amount,
        balance_after_pesewas=wallet.balance_pesewas,
        items=items or [],
        reference=reference,
        created_by=request.user.pk,
    )
    post_entry(
        memo=f"Canteen {kind.replace('_', ' ')}: {wallet.student.full_name}",
        source_type="canteen",
        source_id=str(entry.pk),
        created_by=request.user.pk,
        lines=lines,
    )
    return entry


def top_up(
    *, request: HttpRequest, student: Student, amount: int, reference: str = ""
) -> WalletEntry:
    if not 0 < amount <= MAX_TOP_UP:
        raise ValidationError({"amount_pesewas": "Enter the amount received."})
    if student.status != Student.Status.ACTIVE:
        raise ValidationError({"student": "This pupil isn't on roll."})
    with tenant_atomic():
        wallet = _locked(student)
        entry = _move(
            request=request,
            wallet=wallet,
            kind=WalletEntry.Kind.TOP_UP,
            amount=amount,
            lines=[(CASH, amount, 0), (WALLETS, 0, amount)],
            reference=reference,
        )
        record_event(
            action="canteen.top_up",
            request=request,
            target=student,
            after={"amount_pesewas": amount, "reference": reference},
        )
    return entry


def refund(*, request: HttpRequest, student: Student, amount: int, reason: str) -> WalletEntry:
    if not reason.strip():
        raise ValidationError({"reason": "Say why the money is being given back."})
    with tenant_atomic():
        wallet = _locked(student)
        if not 0 < amount <= wallet.balance_pesewas:
            raise ValidationError({"amount_pesewas": "You can refund up to the wallet balance."})
        entry = _move(
            request=request,
            wallet=wallet,
            kind=WalletEntry.Kind.REFUND,
            amount=-amount,
            lines=[(WALLETS, amount, 0), (CASH, 0, amount)],
            reference=reason[:60],
        )
        record_event(
            action="canteen.refund",
            request=request,
            target=student,
            after={"amount_pesewas": amount, "reason": reason},
        )
    return entry


def spent_today(wallet: Wallet) -> int:
    today = timezone.localdate()
    total = wallet.entries.filter(kind=WalletEntry.Kind.PURCHASE, created_at__date=today).aggregate(
        s=Sum("amount_pesewas")
    )["s"]
    return -(total or 0)


def purchase(
    *, request: HttpRequest, student: Student, basket: list[dict[str, Any]]
) -> WalletEntry:
    """``basket``: [{"item": id, "qty": n}]. Prices come from the menu, not the till."""
    if not basket:
        raise ValidationError({"items": "Add something to sell."})
    menu = {
        m.pk: m
        for m in MenuItem.objects.filter(pk__in=[b["item"] for b in basket], is_available=True)
    }
    items, total = [], 0
    for line in basket:
        item = menu.get(line["item"])
        qty = int(line.get("qty", 1))
        if item is None or not 1 <= qty <= 20:
            raise ValidationError({"items": "One of the items isn't on sale."})
        items.append({"name": item.name, "qty": qty, "price_pesewas": item.price_pesewas})
        total += qty * item.price_pesewas
    low_before = None
    with tenant_atomic():
        wallet = _locked(student)
        if total > wallet.balance_pesewas:
            raise ValidationError(
                {"items": f"Not enough in the wallet (GH₵{wallet.balance_pesewas / 100:,.2f})."}
            )
        if (
            wallet.daily_limit_pesewas is not None
            and spent_today(wallet) + total > wallet.daily_limit_pesewas
        ):
            raise ValidationError({"items": "That would go over today's spending limit."})
        low_before = wallet.balance_pesewas < wallet.low_balance_pesewas
        entry = _move(
            request=request,
            wallet=wallet,
            kind=WalletEntry.Kind.PURCHASE,
            amount=-total,
            lines=[(WALLETS, total, 0), (SALES, 0, total)],
            items=items,
        )
    if not low_before and wallet.balance_pesewas < wallet.low_balance_pesewas:
        from apps.communication.services import notify_guardians

        notify_guardians(
            [student],
            kind="canteen",
            title="Canteen money running low",
            body=(
                f"{student.first_name}'s canteen wallet has "
                f"GH₵{wallet.balance_pesewas / 100:,.2f} left. Top it up at the school office."
            ),
            data={"student_id": str(student.pk)},
        )
    return entry


def on_plan(student: Student) -> MealPlan | None:
    term = current_term()
    return MealPlan.objects.filter(student=student, term=term).first() if term else None


def serve_on_plan(*, request: HttpRequest, student: Student) -> Serving:
    if on_plan(student) is None:
        raise ValidationError({"student": "This pupil isn't on a meal plan this term."})
    try:
        with transaction.atomic(using=require_tenant().db_alias):
            return Serving.objects.create(
                student=student, date=timezone.localdate(), served_by=request.user.pk
            )
    except IntegrityError as exc:
        raise ValidationError({"student": "Already served a plan meal today."}) from exc


def till_view(student: Student) -> dict[str, Any]:
    wallet = wallet_for(student)
    today = timezone.localdate()
    return {
        "student": str(student.pk),
        "name": student.full_name,
        "class": str(student.arm) if student.arm_id else "",
        "balance_pesewas": wallet.balance_pesewas,
        "daily_limit_pesewas": wallet.daily_limit_pesewas,
        "spent_today_pesewas": spent_today(wallet),
        "on_plan": on_plan(student) is not None,
        "served_today": Serving.objects.filter(student=student, date=today).exists(),
    }


def day_summary() -> dict[str, Any]:
    today = timezone.localdate()
    todays = WalletEntry.objects.filter(created_at__date=today)
    sales = -(
        todays.filter(kind=WalletEntry.Kind.PURCHASE).aggregate(s=Sum("amount_pesewas"))["s"] or 0
    )
    top_ups = (
        todays.filter(kind=WalletEntry.Kind.TOP_UP).aggregate(s=Sum("amount_pesewas"))["s"] or 0
    )
    low = Wallet.objects.filter(
        student__status=Student.Status.ACTIVE, balance_pesewas__lt=F("low_balance_pesewas")
    ).count()
    return {
        "date": today,
        "sales_pesewas": sales,
        "purchases": todays.filter(kind=WalletEntry.Kind.PURCHASE).count(),
        "top_ups_pesewas": top_ups,
        "plan_meals": Serving.objects.filter(date=today).count(),
        "held_pesewas": Wallet.objects.aggregate(s=Sum("balance_pesewas"))["s"] or 0,
        "low_wallets": low,
    }
