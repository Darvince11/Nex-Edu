"""Fees, payments and the ledger.

Money rules:
- Integer pesewas everywhere.
- Every money movement posts a balanced journal entry (debits == credits).
- A payment is credited exactly once: the payment row is locked while it is
  applied, and a payment already marked successful is left alone.
- Online payments are credited only after the provider's verify API confirms
  success, the currency is GHS, and the amount.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpRequest
from django.utils import timezone

from apps.academics.models import ClassArm, ClassLevel, Term
from apps.school.services import formatted_number
from apps.students.models import Student
from control_plane.models import PaymentReference, Tenant
from control_plane.tenancy import require_tenant, tenant_atomic, tenant_context
from core.audit.services import record_event
from integrations.payments import PaymentProviderError, VerifiedPayment, provider

from .models import (
    FeeSchedule,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Payment,
    PaymentSettings,
    Scholarship,
)

logger = logging.getLogger(__name__)

CASH, ONLINE_CLEARING, RECEIVABLE, ADVANCE, FEE_INCOME, DISCOUNTS = (
    "1100",
    "1150",
    "1200",
    "2100",
    "4000",
    "4900",
)
DEFAULT_ACCOUNTS = [
    (CASH, "Cash and bank", LedgerAccount.Type.ASSET),
    (ONLINE_CLEARING, "Online payments clearing", LedgerAccount.Type.ASSET),
    (RECEIVABLE, "Fees receivable", LedgerAccount.Type.ASSET),
    (ADVANCE, "Fees paid in advance", LedgerAccount.Type.LIABILITY),
    (FEE_INCOME, "School fee income", LedgerAccount.Type.INCOME),
    (DISCOUNTS, "Discounts and scholarships", LedgerAccount.Type.EXPENSE),
]


class LedgerImbalance(ValueError):
    pass


def seed_ledger_accounts() -> None:
    with tenant_atomic():
        for code, name, kind in DEFAULT_ACCOUNTS:
            LedgerAccount.objects.get_or_create(code=code, defaults={"name": name, "type": kind})


def post_entry(
    *,
    memo: str,
    source_type: str,
    source_id: str,
    lines: list[tuple[str, int, int]],
    created_by: Any = None,
    reverses: JournalEntry | None = None,
    posted_at: Any = None,
) -> JournalEntry:
    """lines: [(account_code, debit_pesewas, credit_pesewas)]. Zero lines are dropped.
    ``posted_at`` dates the entry when it records something that happened earlier."""
    lines = [line for line in lines if line[1] or line[2]]
    debits, credits = sum(d for _, d, _ in lines), sum(c for _, _, c in lines)
    if debits != credits or debits == 0:
        raise LedgerImbalance(f"Debits {debits} != credits {credits} for {source_type} {source_id}")
    accounts = {a.code: a for a in LedgerAccount.objects.filter(code__in=[c for c, _, _ in lines])}
    entry = JournalEntry.objects.create(
        posted_at=posted_at or timezone.now(),
        memo=memo[:200],
        source_type=source_type,
        source_id=str(source_id),
        created_by=created_by,
        reverses=reverses,
    )
    JournalLine.objects.bulk_create(
        [
            JournalLine(entry=entry, account=accounts[code], debit_pesewas=d, credit_pesewas=c)
            for code, d, c in lines
        ]
    )
    return entry


def reverse_entries(source_type: str, source_id: str, *, memo: str, created_by: Any) -> None:
    for entry in JournalEntry.objects.filter(
        source_type=source_type, source_id=str(source_id), reverses__isnull=True
    ).prefetch_related("lines__account"):
        post_entry(
            memo=memo,
            source_type="reversal",
            source_id=str(entry.pk),
            created_by=created_by,
            reverses=entry,
            lines=[
                (line.account.code, line.credit_pesewas, line.debit_pesewas)
                for line in entry.lines.all()
            ],
        )


def account_balances() -> dict[str, int]:
    rows = JournalLine.objects.values("account__code").annotate(
        d=Sum("debit_pesewas"), c=Sum("credit_pesewas")
    )
    return {r["account__code"]: (r["d"] or 0) - (r["c"] or 0) for r in rows}


# --- Invoices -------------------------------------------------------------------


def _students_in_scope(level: ClassLevel | None, arm: ClassArm | None) -> Any:
    qs = Student.objects.filter(status=Student.Status.ACTIVE, arm__isnull=False).select_related(
        "arm"
    )
    if arm:
        qs = qs.filter(arm=arm)
    elif level:
        qs = qs.filter(arm__level=level)
    return qs


def generate_invoices(
    *,
    request: HttpRequest | None,
    term: Term,
    level: ClassLevel | None = None,
    arm: ClassArm | None = None,
    due_date: Any = None,
) -> dict[str, int]:
    """Create one invoice per student from the term's fee schedules. Safe to re-run:
    students who already have a live invoice for the term are skipped."""
    schedules = list(
        FeeSchedule.objects.filter(term=term, is_optional=False).select_related("item")
    )
    if not schedules:
        raise ValidationError("Set up fee schedules for this term first.")
    already = set(
        Invoice.objects.filter(term=term)
        .exclude(status=Invoice.Status.VOID)
        .values_list("student_id", flat=True)
    )
    created = skipped = 0
    actor = getattr(getattr(request, "user", None), "pk", None)
    for student in _students_in_scope(level, arm):
        if student.pk in already:
            skipped += 1
            continue
        lines = [s for s in schedules if s.level_id in (None, student.arm.level_id)]
        gross = sum(s.amount_pesewas for s in lines)
        if not gross:
            skipped += 1
            continue
        # Scholarships come off as their own lines, each capped so the bill never goes negative.
        reductions: list[tuple[str, int]] = []
        remaining = gross
        for scholarship in Scholarship.objects.filter(student=student, is_active=True):
            off = min(
                scholarship.deduction([(s.item_id, s.amount_pesewas) for s in lines]), remaining
            )
            if off > 0:
                reductions.append((f"Scholarship: {scholarship.name}", off))
                remaining -= off
        total = gross - sum(off for _, off in reductions)
        with tenant_atomic():
            invoice = Invoice.objects.create(
                number=formatted_number("invoice", "INV"),
                student=student,
                term=term,
                total_pesewas=total,
                due_date=due_date,
                issued_at=timezone.now(),
            )
            InvoiceLine.objects.bulk_create(
                [
                    InvoiceLine(
                        invoice=invoice,
                        item=s.item,
                        description=s.item.name,
                        amount_pesewas=s.amount_pesewas,
                    )
                    for s in lines
                ]
                + [
                    InvoiceLine(invoice=invoice, description=label[:120], amount_pesewas=-off)
                    for label, off in reductions
                ]
            )
            discount = gross - total
            post_entry(
                memo=f"Invoice {invoice.number}",
                source_type="invoice",
                source_id=str(invoice.pk),
                created_by=actor,
                lines=[(RECEIVABLE, total, 0), (FEE_INCOME, 0, gross)]
                + ([(DISCOUNTS, discount, 0)] if discount else []),
            )
        created += 1
    with tenant_atomic():
        record_event(
            action="finance.invoices_generated",
            request=request,
            target=term,
            after={
                "created": created,
                "skipped": skipped,
                "level": str(level) if level else None,
                "arm": str(arm) if arm else None,
            },
        )
    return {"created": created, "skipped": skipped}


def add_discount(
    *, request: HttpRequest | None, invoice: Invoice, description: str, amount_pesewas: int
) -> Invoice:
    if amount_pesewas <= 0:
        raise ValidationError("Enter the discount as a positive amount.")
    with tenant_atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status == Invoice.Status.VOID:
            raise ValidationError("This invoice is void.")
        if amount_pesewas > invoice.balance_pesewas:
            raise ValidationError("A discount can't exceed the outstanding balance.")
        InvoiceLine.objects.create(
            invoice=invoice, description=description[:120], amount_pesewas=-amount_pesewas
        )
        invoice.total_pesewas -= amount_pesewas
        _refresh_status(invoice)
        invoice.save(update_fields=["total_pesewas", "status"])
        post_entry(
            memo=f"Discount on {invoice.number}: {description}",
            source_type="invoice",
            source_id=str(invoice.pk),
            created_by=request.user.pk if request else None,
            lines=[(DISCOUNTS, amount_pesewas, 0), (RECEIVABLE, 0, amount_pesewas)],
        )
        record_event(
            action="finance.discount_added",
            request=request,
            target=invoice,
            after={"description": description, "amount_pesewas": amount_pesewas},
        )
    return invoice


def void_invoice(*, request: HttpRequest | None, invoice: Invoice, reason: str) -> Invoice:
    if not reason.strip():
        raise ValidationError("A reason is required to void an invoice.")
    with tenant_atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.paid_pesewas:
            raise ValidationError("This invoice has payments. Refund them before voiding.")
        if invoice.status == Invoice.Status.VOID:
            return invoice
        invoice.status = Invoice.Status.VOID
        invoice.save(update_fields=["status"])
        reverse_entries(
            "invoice",
            str(invoice.pk),
            memo=f"Void {invoice.number}: {reason}",
            created_by=request.user.pk if request else None,
        )
        record_event(
            action="finance.invoice_voided", request=request, target=invoice, reason=reason
        )
    return invoice


def _refresh_status(invoice: Invoice) -> None:
    if invoice.status == Invoice.Status.VOID:
        return
    if invoice.paid_pesewas >= invoice.total_pesewas:
        invoice.status = Invoice.Status.PAID
    elif invoice.paid_pesewas > 0:
        invoice.status = Invoice.Status.PART_PAID
    else:
        invoice.status = Invoice.Status.ISSUED


# --- Payments -------------------------------------------------------------------


def _credit(payment: Payment, received_pesewas: int, debit_account: str, actor: Any) -> None:
    """Apply received money to the invoice and post the entry. Caller holds row locks."""
    invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
    applied = min(received_pesewas, invoice.balance_pesewas)
    excess = received_pesewas - applied
    invoice.paid_pesewas += applied
    _refresh_status(invoice)
    invoice.save(update_fields=["paid_pesewas", "status"])
    payment.status = Payment.Status.SUCCESS
    payment.amount_received_pesewas = received_pesewas
    payment.paid_at = payment.paid_at or timezone.now()
    payment.receipt_number = formatted_number("receipt", "RCT")
    payment.save()
    post_entry(
        memo=f"Payment {payment.receipt_number} for {invoice.number}",
        source_type="payment",
        source_id=str(payment.pk),
        created_by=actor,
        lines=[
            (debit_account, received_pesewas, 0),
            (RECEIVABLE, 0, applied),
            (ADVANCE, 0, excess),
        ],
    )


def record_manual_payment(
    *,
    request: HttpRequest | None,
    invoice: Invoice,
    amount_pesewas: int,
    method: str,
    reference: str,
    note: str = "",
    paid_at: Any = None,
) -> Payment:
    if method not in {Payment.Method.CASH, Payment.Method.BANK_TRANSFER, Payment.Method.POS}:
        raise ValidationError("Manual payments must be cash, bank transfer or POS.")
    if amount_pesewas <= 0:
        raise ValidationError("Amount must be positive.")
    actor = request.user.pk if request else None
    with tenant_atomic():
        if invoice.status == Invoice.Status.VOID:
            raise ValidationError("This invoice is void.")
        payment = Payment.objects.create(
            invoice=invoice,
            method=method,
            amount_pesewas=amount_pesewas,
            reference=reference or f"MAN-{uuid.uuid4().hex[:16].upper()}",
            note=note[:200],
            recorded_by=actor,
            paid_at=paid_at or timezone.now(),
        )
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        _credit(payment, amount_pesewas, CASH, actor)
        record_event(
            action="finance.payment_recorded",
            request=request,
            target=payment,
            after={"invoice": invoice.number, "amount_pesewas": amount_pesewas, "method": method},
        )
    _after_success(payment)
    _payment_event(payment)
    return payment


def start_online_payment(
    *,
    request: HttpRequest,
    invoice: Invoice,
    provider_name: str,
    amount_pesewas: int | None,
    idempotency_key: str,
    email: str,
) -> Payment:
    if not idempotency_key or len(idempotency_key) > 80:
        raise ValidationError("An Idempotency-Key header (up to 80 characters) is required.")
    if existing := Payment.objects.filter(idempotency_key=idempotency_key).first():
        if existing.invoice_id != invoice.pk:
            raise ValidationError("This Idempotency-Key was already used for another invoice.")
        return existing

    cfg = PaymentSettings.load()
    if not cfg.online_payments_enabled:
        raise ValidationError("This school does not accept online payments yet.")
    if invoice.status in {Invoice.Status.VOID, Invoice.Status.PAID}:
        raise ValidationError("This invoice is not payable.")
    balance = invoice.balance_pesewas
    amount = amount_pesewas or balance
    if amount > balance:
        raise ValidationError("You can't pay more than the outstanding balance.")
    if amount < balance and not cfg.allow_part_payment:
        raise ValidationError("This school requires payment in full.")
    if amount < balance and amount < cfg.minimum_part_payment_pesewas:
        raise ValidationError("The amount is below the school's minimum part payment.")
    if not email:
        raise ValidationError("An email address is needed for the payment receipt.")

    tenant = require_tenant()
    reference = f"NXE{uuid.uuid4().hex[:21].upper()}"
    subaccount = (
        cfg.paystack_subaccount_code
        if provider_name == "paystack"
        else cfg.flutterwave_subaccount_id
    )
    # Control-plane index first, so a fast webhook can always find the school.
    PaymentReference.objects.create(reference=reference, tenant=tenant, provider=provider_name)
    with tenant_atomic():
        payment = Payment.objects.create(
            invoice=invoice,
            method=provider_name,
            amount_pesewas=amount,
            reference=reference,
            idempotency_key=idempotency_key,
            payer_user_id=request.user.pk,
            payer_email=email,
        )
    try:
        checkout = provider(provider_name).initialize(
            reference=reference,
            amount_pesewas=amount,
            email=email,
            callback_url=f"{settings.FRONTEND_URL}/payments/return?reference={reference}",
            subaccount=subaccount,
            metadata={"invoice": invoice.number, "school": tenant.slug},
        )
    except PaymentProviderError:
        Payment.objects.filter(pk=payment.pk).update(status=Payment.Status.FAILED)
        raise
    Payment.objects.filter(pk=payment.pk).update(authorization_url=checkout.authorization_url)
    payment.authorization_url = checkout.authorization_url
    with tenant_atomic():
        record_event(
            action="finance.online_payment_started",
            request=request,
            target=payment,
            after={"invoice": invoice.number, "amount_pesewas": amount, "provider": provider_name},
        )
    return payment


def apply_verified(payment_id: Any, verified: VerifiedPayment) -> Payment:
    """Credit a verified online payment exactly once."""
    with tenant_atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.status == Payment.Status.SUCCESS:
            return payment
        if not verified.succeeded:
            if verified.status in {"failed", "abandoned", "reversed", "cancelled"}:
                payment.status = (
                    Payment.Status.ABANDONED
                    if verified.status == "abandoned"
                    else Payment.Status.FAILED
                )
                payment.provider_payload = verified.raw
                payment.save(update_fields=["status", "provider_payload"])
            return payment
        if verified.reference != payment.reference:
            raise PaymentProviderError("Provider returned a different reference")
        if verified.currency != "GHS":
            raise PaymentProviderError(f"Unexpected currency {verified.currency}")
        received = verified.amount_pesewas
        if received < payment.amount_pesewas:
            payment.note = f"Received {received} pesewas of {payment.amount_pesewas} requested"
        payment.provider_transaction_id = verified.provider_transaction_id
        payment.provider_payload = verified.raw
        payment.paid_at = verified.paid_at or timezone.now()
        _credit(payment, received, ONLINE_CLEARING, None)
        record_event(
            action="finance.online_payment_succeeded",
            target=payment,
            after={
                "amount_pesewas": received,
                "provider": payment.method,
                "transaction": verified.provider_transaction_id,
            },
        )
    _after_success(payment)
    _payment_event(payment)
    return payment


def _payment_event(payment: Payment) -> None:
    from control_plane.api.developer import payment_data
    from control_plane.developer import emit

    emit("payment.received", payment_data(payment))


def verify_payment(payment: Payment) -> Payment:
    if payment.method not in Payment.ONLINE or payment.status == Payment.Status.SUCCESS:
        return payment
    return apply_verified(payment.pk, provider(payment.method).verify(payment.reference))


def process_webhook(provider_name: str, raw_body: bytes, headers: Any) -> str:
    """Returns a short outcome string. Raises PermissionDenied for a bad signature."""
    client = provider(provider_name)
    if not client.webhook_is_authentic(raw_body, headers):
        raise PermissionDenied("Invalid webhook signature")
    try:
        payload = json.loads(raw_body)
    except ValueError:
        return "ignored: not json"
    reference = client.reference_from_webhook(payload)
    if not reference:
        return "ignored: event"
    if provider_name == "paystack":
        from control_plane.subscriptions import handle_webhook_reference

        # A school paying Nex Edu, not a parent paying the school.
        if (outcome := handle_webhook_reference(reference)) is not None:
            return outcome
    index = (
        PaymentReference.objects.select_related("tenant")
        .filter(reference=reference, provider=provider_name)
        .first()
    )
    if index is None or index.tenant.status != Tenant.Status.ACTIVE:
        return "ignored: unknown reference"
    with tenant_context(index.tenant):
        payment = Payment.objects.filter(reference=reference).first()
        if payment is None:
            return "ignored: no payment"
        payment = verify_payment(payment)
        return f"payment {payment.status}"


def reconcile_pending_payments() -> dict[str, int]:
    """Catch webhooks that never arrived: re-verify recent pending payments,
    and abandon ones older than two days. Runs for the current school."""
    now = timezone.now()
    counts = {"verified": 0, "abandoned": 0, "errors": 0}
    pending = Payment.objects.filter(
        status=Payment.Status.PENDING,
        method__in=list(Payment.ONLINE),
        created_at__lte=now - timedelta(minutes=10),
    )
    for payment in pending:
        if payment.created_at < now - timedelta(days=2):
            Payment.objects.filter(pk=payment.pk, status=Payment.Status.PENDING).update(
                status=Payment.Status.ABANDONED
            )
            counts["abandoned"] += 1
            continue
        try:
            verify_payment(payment)
            counts["verified"] += 1
        except PaymentProviderError:
            logger.warning("Reconcile failed for %s", payment.reference)
            counts["errors"] += 1
    return counts


def _after_success(payment: Payment) -> None:
    from apps.communication.models import Channel
    from apps.communication.services import notify_guardians

    def notify() -> None:
        invoice = payment.invoice
        cedis = f"GH₵{payment.amount_received_pesewas / 100:,.2f}"
        notify_guardians(
            [invoice.student],
            kind="payment",
            title="Payment received",
            body=f"{cedis} received for {invoice.student.first_name}'s fees ({invoice.number}). "
            f"Receipt {payment.receipt_number}. Balance GH₵{invoice.balance_pesewas / 100:,.2f}.",
            data={"payment_id": str(payment.pk)},
            channels={Channel.EMAIL},
        )

    transaction.on_commit(notify, using=require_tenant().db_alias)


def ensure_can_pay(user: Any, permissions: frozenset[str], invoice: Invoice) -> None:
    from core.rbac import Perm

    if Perm.FINANCE_MANAGE in permissions:
        return
    if (
        Perm.FINANCE_PAY not in permissions
        or not invoice.student.guardians.filter(guardian_user_id=user.pk).exists()
    ):
        raise PermissionDenied("You can only pay invoices for your own children.")


def term_summary(term: Term) -> dict[str, Any]:
    live = Invoice.objects.filter(term=term).exclude(status=Invoice.Status.VOID)
    totals = live.aggregate(billed=Sum("total_pesewas"), collected=Sum("paid_pesewas"))
    billed, collected = totals["billed"] or 0, totals["collected"] or 0
    by_status = {
        s: live.filter(status=s).count()
        for s in (Invoice.Status.ISSUED, Invoice.Status.PART_PAID, Invoice.Status.PAID)
    }
    online = Payment.objects.filter(invoice__term=term, status=Payment.Status.SUCCESS).filter(
        Q(method__in=list(Payment.ONLINE))
    )
    return {
        "billed_pesewas": billed,
        "collected_pesewas": collected,
        "outstanding_pesewas": billed - collected,
        "invoices": by_status,
        "online_payments": online.count(),
    }
