"""Monthly subscription invoices, online payment by the proprietor, and SMS bundles.

Owner's decisions (26 Oct 2026): band prices are per month; an invoice unpaid 30
days after its due date suspends the school until it is paid; SMS beyond a small
monthly allowance comes from bundles the school buys.

The month's invoice is made on the 1st from the school's latest pupil count (its
band) plus any paid add-on modules Nex Edu granted. Payments come in through the
same Paystack webhook as school fees; references starting ``NXS-`` are ours, so
they never reach a school's database.
"""

from __future__ import annotations

import datetime as dt
import logging
import secrets
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from control_plane import lifecycle
from control_plane.audit import record_platform_event
from control_plane.models import (
    BillingSettings,
    SmsBundle,
    SmsCredit,
    SubscriptionCharge,
    SubscriptionInvoice,
    SubscriptionPayment,
    Tenant,
    TenantModule,
)
from control_plane.pricing import band_for, price_bands
from control_plane.usage import latest_usage
from integrations.payments import PaymentProviderError, provider

logger = logging.getLogger(__name__)

PREFIX = "NXS-"
SUSPEND_AFTER_DAYS = 30
REMINDER_DAYS = (7, 14)
PROVIDER = "paystack"


def month_start(day: dt.date) -> dt.date:
    return day.replace(day=1)


def _lines(tenant: Tenant, month: dt.date) -> tuple[list[dict[str, Any]], str, int | None]:
    from control_plane.modules import prices
    from core.modules import BY_CODE

    usage = latest_usage([tenant]).get(tenant.pk)
    pupils = usage.pupils if usage else 0
    band = band_for(pupils, price_bands())
    lines = [
        {
            "description": f"Nex Edu, {month:%B %Y}: {band.label.lower()} ({pupils} pupils)",
            "amount_pesewas": band.price_pesewas,
        }
    ]
    cost = prices()
    for row in TenantModule.objects.filter(tenant=tenant, granted=True).order_by("code"):
        if cost.get(row.code, 0) > 0:
            name = BY_CODE[row.code].name if row.code in BY_CODE else row.code
            lines.append({"description": f"Add-on: {name}", "amount_pesewas": cost[row.code]})
    return lines, band.code, usage.pupils if usage else None


def issue_invoice(
    tenant: Tenant, month: dt.date, *, today: dt.date | None = None
) -> SubscriptionInvoice | None:
    """The month's invoice for one school; None if it already has one."""
    today = today or timezone.localdate()
    month = month_start(month)
    if (
        SubscriptionInvoice.objects.filter(tenant=tenant, month=month)
        .exclude(status=SubscriptionInvoice.Status.VOID)
        .exists()
    ):
        return None
    lines, band_code, pupils = _lines(tenant, month)
    due_days = BillingSettings.load().due_days
    try:
        with transaction.atomic():
            invoice = SubscriptionInvoice.objects.create(
                number=f"NXI-{month:%Y%m}-{tenant.slug}"[:30],
                tenant=tenant,
                month=month,
                band_code=band_code,
                pupils=pupils,
                lines=lines,
                total_pesewas=sum(line["amount_pesewas"] for line in lines),
                issued_on=today,
                due_on=today + dt.timedelta(days=due_days),
            )
            record_platform_event(
                action="billing.invoice_issued",
                tenant=tenant,
                target=invoice,
                data={"number": invoice.number, "total_pesewas": invoice.total_pesewas},
            )
    except IntegrityError:
        return None  # made at the same moment by another worker
    _email(
        tenant,
        f"Nex Edu invoice {invoice.number}",
        f"Your Nex Edu invoice for {month:%B %Y} is GH₵{invoice.total_pesewas / 100:,.2f}, "
        f"due on {invoice.due_on:%d %B %Y}.\n\nPay by mobile money or card: {_billing_url(tenant)}",
    )
    return invoice


def issue_month(today: dt.date | None = None) -> int:
    """Daily job: make this month's invoice for every active school that lacks one."""
    today = today or timezone.localdate()
    made = 0
    for tenant in Tenant.objects.filter(status=Tenant.Status.ACTIVE):
        made += issue_invoice(tenant, today, today=today) is not None
    return made


def _billing_url(tenant: Tenant) -> str:
    return f"{settings.FRONTEND_URL}/account/billing?school={tenant.slug}"


def _email(tenant: Tenant, subject: str, body: str) -> None:
    emails = lifecycle.owner_emails(tenant)
    if emails:
        send_mail(subject, body, None, emails, fail_silently=True)


def chase_overdue(today: dt.date | None = None) -> dict[str, int]:
    """Daily job: reminders at 7 and 14 days overdue; suspension at 30."""
    today = today or timezone.localdate()
    counts = {"reminded": 0, "suspended": 0}
    for invoice in SubscriptionInvoice.objects.filter(
        status=SubscriptionInvoice.Status.OPEN, due_on__lt=today
    ).select_related("tenant"):
        late = (today - invoice.due_on).days
        tenant = invoice.tenant
        if late >= SUSPEND_AFTER_DAYS and tenant.status == Tenant.Status.ACTIVE:
            lifecycle.suspend(
                tenant,
                reason=lifecycle.Reason.NONPAYMENT,
                note=f"Invoice {invoice.number} is {late} days overdue.",
                automatic=True,
            )
            counts["suspended"] += 1
            continue
        due_reminders = sum(1 for d in REMINDER_DAYS if late >= d)
        if due_reminders > invoice.reminders_sent and tenant.status == Tenant.Status.ACTIVE:
            SubscriptionInvoice.objects.filter(pk=invoice.pk).update(reminders_sent=due_reminders)
            left = SUSPEND_AFTER_DAYS - late
            _email(
                tenant,
                f"Overdue: Nex Edu invoice {invoice.number}",
                f"Invoice {invoice.number} (GH₵{invoice.total_pesewas / 100:,.2f}) was due on "
                f"{invoice.due_on:%d %B %Y}. If it isn't paid within {left} days, "
                f"{tenant.name} will be suspended until it is.\n\nPay now: {_billing_url(tenant)}",
            )
            counts["reminded"] += 1
    return counts


@transaction.atomic
def mark_paid(
    invoice: SubscriptionInvoice,
    *,
    method: str,
    reference: str = "",
    request: Any = None,
    recorded_by: Any = None,
    received_on: dt.date | None = None,
) -> SubscriptionPayment:
    invoice = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != SubscriptionInvoice.Status.OPEN:
        raise ValidationError({"detail": "This invoice isn't waiting for payment."})
    on = received_on or timezone.localdate()
    payment = SubscriptionPayment.objects.create(
        tenant=invoice.tenant,
        invoice=invoice,
        amount_pesewas=invoice.total_pesewas,
        period_label=f"{invoice.month:%B %Y}",
        method=method,
        reference=reference,
        received_on=on,
        band_code=invoice.band_code,
        pupils=invoice.pupils,
        recorded_by=recorded_by,
    )
    invoice.status, invoice.paid_on = SubscriptionInvoice.Status.PAID, on
    invoice.save(update_fields=["status", "paid_on"])
    record_platform_event(
        action="billing.invoice_paid",
        request=request,
        tenant=invoice.tenant,
        target=invoice,
        data={"number": invoice.number, "method": method, "amount_pesewas": payment.amount_pesewas},
    )
    _reactivate_if_settled(invoice.tenant)
    return payment


def _reactivate_if_settled(tenant: Tenant) -> None:
    """A school suspended for not paying comes back once nothing is 30 days overdue."""
    tenant.refresh_from_db()
    if (
        tenant.status != Tenant.Status.SUSPENDED
        or tenant.status_reason != lifecycle.Reason.NONPAYMENT
    ):
        return
    cutoff = timezone.localdate() - dt.timedelta(days=SUSPEND_AFTER_DAYS)
    if not SubscriptionInvoice.objects.filter(
        tenant=tenant, status=SubscriptionInvoice.Status.OPEN, due_on__lte=cutoff
    ).exists():
        lifecycle.reactivate(tenant, note="Overdue invoices paid", automatic=True)


@transaction.atomic
def void(invoice: SubscriptionInvoice, *, reason: str, request: Any) -> SubscriptionInvoice:
    if not reason.strip():
        raise ValidationError({"reason": "Say why the invoice is cancelled."})
    invoice = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != SubscriptionInvoice.Status.OPEN:
        raise ValidationError({"detail": "Only an unpaid invoice can be cancelled."})
    invoice.status, invoice.void_reason = SubscriptionInvoice.Status.VOID, reason.strip()
    invoice.save(update_fields=["status", "void_reason"])
    record_platform_event(
        action="billing.invoice_voided",
        request=request,
        tenant=invoice.tenant,
        target=invoice,
        data={"number": invoice.number},
        reason=reason.strip(),
    )
    _reactivate_if_settled(invoice.tenant)
    return invoice


# --- Paying online -----------------------------------------------------------------------


def start_checkout(
    *,
    request: Any,
    tenant: Tenant,
    invoice: SubscriptionInvoice | None = None,
    bundle: SmsBundle | None = None,
) -> SubscriptionCharge:
    if (invoice is None) == (bundle is None):
        raise ValidationError({"detail": "Choose an invoice or an SMS bundle."})
    if invoice is not None:
        if invoice.tenant_id != tenant.pk or invoice.status != SubscriptionInvoice.Status.OPEN:
            raise ValidationError({"detail": "This invoice isn't waiting for payment."})
        amount = invoice.total_pesewas
    elif bundle is not None:
        if not bundle.is_active:
            raise ValidationError({"detail": "This bundle isn't on sale."})
        if tenant.status != Tenant.Status.ACTIVE:
            raise ValidationError({"detail": "Pay what's overdue first."})
        amount = bundle.price_pesewas
    reference = f"{PREFIX}{secrets.token_hex(8).upper()}"
    charge = SubscriptionCharge.objects.create(
        reference=reference,
        tenant=tenant,
        invoice=invoice,
        bundle=bundle,
        sms=bundle.sms if bundle else 0,
        amount_pesewas=amount,
        created_by=request.user,
    )
    try:
        checkout = provider(PROVIDER).initialize(
            reference=reference,
            amount_pesewas=amount,
            email=request.user.email,
            callback_url=f"{_billing_url(tenant)}&reference={reference}",
            subaccount="",  # Nex Edu's own account, not the school's
            metadata={"school": tenant.slug, "kind": "invoice" if invoice else "sms_bundle"},
        )
    except PaymentProviderError:
        SubscriptionCharge.objects.filter(pk=charge.pk).update(
            status=SubscriptionCharge.Status.FAILED
        )
        raise
    SubscriptionCharge.objects.filter(pk=charge.pk).update(
        authorization_url=checkout.authorization_url
    )
    charge.authorization_url = checkout.authorization_url
    record_platform_event(
        action="billing.checkout_started",
        request=request,
        tenant=tenant,
        target=charge,
        data={"reference": reference, "amount_pesewas": amount},
    )
    return charge


def verify_charge(charge: SubscriptionCharge) -> SubscriptionCharge:
    """Ask Paystack; on success pay the invoice or add the SMS. Safe to repeat."""
    if charge.status != SubscriptionCharge.Status.PENDING:
        return charge
    result = provider(PROVIDER).verify(charge.reference)
    if not result.succeeded:
        if result.status in ("failed", "abandoned", "reversed"):
            SubscriptionCharge.objects.filter(
                pk=charge.pk, status=SubscriptionCharge.Status.PENDING
            ).update(status=SubscriptionCharge.Status.FAILED)
        charge.refresh_from_db()
        return charge
    if result.currency != "GHS" or result.amount_pesewas != charge.amount_pesewas:
        logger.error(
            "Charge %s: Paystack amount %s doesn't match", charge.reference, result.amount_pesewas
        )
        record_platform_event(
            action="billing.charge_mismatch",
            tenant=charge.tenant,
            target=charge,
            data={"paid_pesewas": result.amount_pesewas, "expected_pesewas": charge.amount_pesewas},
        )
        return charge
    with transaction.atomic():
        locked = SubscriptionCharge.objects.select_for_update().get(pk=charge.pk)
        if locked.status != SubscriptionCharge.Status.PENDING:
            return locked
        locked.status = SubscriptionCharge.Status.PAID
        locked.paid_at = result.paid_at or timezone.now()
        locked.provider_transaction_id = result.provider_transaction_id
        locked.save(update_fields=["status", "paid_at", "provider_transaction_id"])
        invoice = locked.invoice
        if invoice is not None:
            if invoice.status == SubscriptionInvoice.Status.OPEN:
                mark_paid(
                    invoice, method=SubscriptionPayment.Method.PAYSTACK, reference=locked.reference
                )
        else:
            add_sms(locked.tenant, locked.sms)
            SubscriptionPayment.objects.create(
                tenant=locked.tenant,
                amount_pesewas=locked.amount_pesewas,
                period_label=f"SMS bundle: {locked.sms:,} SMS",
                method=SubscriptionPayment.Method.PAYSTACK,
                reference=locked.reference,
                received_on=timezone.localdate(),
            )
            record_platform_event(
                action="billing.sms_bought",
                tenant=locked.tenant,
                target=locked,
                data={"sms": locked.sms, "amount_pesewas": locked.amount_pesewas},
            )
    return locked


def handle_webhook_reference(reference: str) -> str | None:
    """Our reference? Verify and apply. None means it belongs to a school's fees."""
    if not reference.startswith(PREFIX):
        return None
    charge = SubscriptionCharge.objects.filter(reference=reference).first()
    if charge is None:
        return "ignored: unknown subscription reference"
    return f"subscription {verify_charge(charge).status}"


def reconcile_charges() -> int:
    """Catch webhooks that never came: re-check recent pending charges, give up after 2 days."""
    now = timezone.now()
    done = 0
    for charge in SubscriptionCharge.objects.filter(
        status=SubscriptionCharge.Status.PENDING, created_at__lte=now - dt.timedelta(minutes=10)
    ):
        if charge.created_at < now - dt.timedelta(days=2):
            SubscriptionCharge.objects.filter(pk=charge.pk).update(
                status=SubscriptionCharge.Status.ABANDONED
            )
            continue
        try:
            done += verify_charge(charge).status == SubscriptionCharge.Status.PAID
        except PaymentProviderError:
            logger.warning("Could not verify subscription charge %s", charge.reference)
    return done


# --- SMS allowance and bundles ------------------------------------------------------------


def add_sms(tenant: Tenant, count: int) -> None:
    credit, _ = SmsCredit.objects.get_or_create(tenant=tenant)
    SmsCredit.objects.filter(pk=credit.pk).update(balance=F("balance") + count)


def sms_allowance(tenant: Tenant) -> dict[str, int]:
    """What the school may send: the monthly allowance plus bought SMS not used yet."""
    credit = SmsCredit.objects.filter(tenant=tenant).values_list("balance", flat=True).first()
    return {"monthly": BillingSettings.load().sms_included_monthly, "bought": credit or 0}


def use_bought_sms(tenant: Tenant, count: int) -> None:
    """Take SMS sent beyond the monthly allowance off the bought balance."""
    if count > 0:
        # One statement, so it can't race another sending job or go below nothing.
        SmsCredit.objects.filter(tenant=tenant).update(
            balance=Greatest(F("balance") - count, Value(0))
        )


def account(tenant: Tenant) -> dict[str, Any]:
    """What the proprietor sees on the billing page."""
    invoices = SubscriptionInvoice.objects.filter(tenant=tenant).exclude(
        status=SubscriptionInvoice.Status.VOID
    )
    today = timezone.localdate()
    usage = latest_usage([tenant]).get(tenant.pk)
    band = band_for(usage.pupils if usage else 0, price_bands())
    return {
        "school": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "status_reason": tenant.status_reason,
        "purge_after": tenant.purge_after,
        "export_ready": bool(tenant.export_key) and not tenant.purged_at,
        "band": {"label": band.label, "price_pesewas": band.price_pesewas},
        "outstanding_pesewas": sum(
            i.total_pesewas for i in invoices if i.status == SubscriptionInvoice.Status.OPEN
        ),
        "invoices": [
            {
                "id": str(i.pk),
                "number": i.number,
                "month": i.month,
                "lines": i.lines,
                "total_pesewas": i.total_pesewas,
                "issued_on": i.issued_on,
                "due_on": i.due_on,
                "status": i.status,
                "overdue_days": max((today - i.due_on).days, 0)
                if i.status == SubscriptionInvoice.Status.OPEN
                else 0,
                "paid_on": i.paid_on,
            }
            for i in invoices[:36]
        ],
        "sms": {**sms_allowance(tenant), "sent_this_month": usage.sms_sent_month if usage else 0},
        "bundles": [
            {"code": b.code, "label": b.label, "sms": b.sms, "price_pesewas": b.price_pesewas}
            for b in SmsBundle.objects.filter(is_active=True)
        ],
    }
