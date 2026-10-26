"""School fees: schedules, invoices, payments and a double-entry ledger.

Every amount is an integer number of pesewas (GH₵1 = 100 pesewas), never a float.
Ledger entries are immutable; a correction is a reversing entry.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.db import models

from apps.academics.models import ClassLevel, Term
from apps.students.models import Student
from core.audit.models import AppendOnlyError


class PaymentSettings(models.Model):
    """Per-school payment configuration (singleton).

    Money settles directly to the school's bank through a Paystack subaccount or a
    Flutterwave subaccount; the platform never holds school funds.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    online_payments_enabled = models.BooleanField(default=False)
    paystack_subaccount_code = models.CharField(max_length=40, blank=True)
    flutterwave_subaccount_id = models.CharField(max_length=40, blank=True)
    allow_part_payment = models.BooleanField(default=True)
    minimum_part_payment_pesewas = models.PositiveBigIntegerField(default=0)
    bank_transfer_instructions = models.TextField(blank=True)

    @classmethod
    def load(cls) -> PaymentSettings:
        return cls.objects.get_or_create(pk=1)[0]


class FeeItem(models.Model):
    name = models.CharField(max_length=80, unique=True)  # "Tuition", "PTA levy"
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class FeeSchedule(models.Model):
    """What a fee costs in a term, for one class level or (level empty) everyone."""

    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="fee_schedules")
    level = models.ForeignKey(
        ClassLevel, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    item = models.ForeignKey(FeeItem, on_delete=models.PROTECT, related_name="schedules")
    amount_pesewas = models.PositiveBigIntegerField()
    is_optional = models.BooleanField(default=False)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["term", "level", "item"], name="uniq_fee_schedule")
        ]


class Invoice(models.Model):
    class Status(models.TextChoices):
        ISSUED = "issued"
        PART_PAID = "part_paid"
        PAID = "paid"
        VOID = "void"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=30, unique=True)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="invoices")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="invoices")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED)
    total_pesewas = models.BigIntegerField()
    paid_pesewas = models.BigIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    issued_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-issued_at"]
        constraints: ClassVar = [
            # One live invoice per student per term; regenerate after voiding.
            models.UniqueConstraint(
                fields=["student", "term"],
                condition=~models.Q(status="void"),
                name="one_live_invoice_per_term",
            ),
        ]
        indexes: ClassVar = [models.Index(fields=["term", "status"])]

    @property
    def balance_pesewas(self) -> int:
        return max(self.total_pesewas - self.paid_pesewas, 0)


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(FeeItem, on_delete=models.PROTECT, null=True, blank=True)
    description = models.CharField(max_length=120)
    amount_pesewas = models.BigIntegerField(help_text="Negative for a discount or scholarship")


class Payment(models.Model):
    class Method(models.TextChoices):
        PAYSTACK = "paystack"
        FLUTTERWAVE = "flutterwave"
        CASH = "cash"
        BANK_TRANSFER = "bank_transfer"
        POS = "pos"

    class Status(models.TextChoices):
        PENDING = "pending"
        SUCCESS = "success"
        FAILED = "failed"
        ABANDONED = "abandoned"

    ONLINE = frozenset({Method.PAYSTACK, Method.FLUTTERWAVE})

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=15, choices=Method.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    amount_pesewas = models.PositiveBigIntegerField(help_text="Amount requested or recorded")
    amount_received_pesewas = models.PositiveBigIntegerField(default=0)
    reference = models.CharField(max_length=60, unique=True)
    idempotency_key = models.CharField(max_length=80, unique=True, null=True, blank=True)
    provider_transaction_id = models.CharField(max_length=60, blank=True)
    authorization_url = models.URLField(max_length=500, blank=True)
    payer_user_id = models.UUIDField(null=True, blank=True)
    payer_email = models.EmailField(blank=True)
    recorded_by = models.UUIDField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    receipt_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    provider_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["status", "created_at"])]


class LedgerAccount(models.Model):
    class Type(models.TextChoices):
        ASSET = "asset"
        LIABILITY = "liability"
        INCOME = "income"
        EXPENSE = "expense"

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=80)
    type = models.CharField(max_length=10, choices=Type.choices)

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class JournalEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    posted_at = models.DateTimeField()
    memo = models.CharField(max_length=200)
    source_type = models.CharField(max_length=30)  # "invoice", "payment", "reversal"
    source_id = models.CharField(max_length=64, db_index=True)
    reverses = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by"
    )
    created_by = models.UUIDField(null=True, blank=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AppendOnlyError("Journal entries are immutable; post a reversal instead.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise AppendOnlyError("Journal entries are immutable; post a reversal instead.")


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="lines")
    debit_pesewas = models.PositiveBigIntegerField(default=0)
    credit_pesewas = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=(
                    models.Q(debit_pesewas__gt=0, credit_pesewas=0)
                    | models.Q(debit_pesewas=0, credit_pesewas__gt=0)
                ),
                name="line_is_debit_xor_credit",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AppendOnlyError("Journal lines are immutable.")
        super().save(*args, **kwargs)


class Scholarship(models.Model):
    """A standing reduction on a pupil's fees, applied whenever invoices are made:
    a percentage or a fixed amount, of the whole bill or of one fee item."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="scholarships")
    name = models.CharField(max_length=80, help_text='e.g. "Staff child", "Sibling discount"')
    percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    amount_pesewas = models.PositiveBigIntegerField(null=True, blank=True)
    item = models.ForeignKey(
        FeeItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Only this fee item; empty means the whole bill",
    )
    is_active = models.BooleanField(default=True)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["student__last_name", "name"]

    def deduction(self, lines: list[tuple[Any, int]]) -> int:
        """Pesewas off, given the invoice lines as (fee item id, amount)."""
        base = sum(amount for item_id, amount in lines if self.item_id in (None, item_id))
        if base <= 0:
            return 0
        if self.percent is not None:
            return min(base, round(base * float(self.percent) / 100))
        return min(base, self.amount_pesewas or 0)
