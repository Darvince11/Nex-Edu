"""Payroll: each member of staff's pay, the tax and SSNIT rules, monthly pay runs and
payslips. Money in pesewas. Salaries are confidential: only the proprietor and the
bursar see them; each member of staff sees their own payslips."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import ClassVar

from django.db import models

from apps.staff.models import StaffProfile
from core.crypto import EncryptedTextField

#: Monthly PAYE bands for resident individuals from 1 September 2026 (Income Tax
#: (Amendment) Act, 2026, Act 1178), as [band width in pesewas (None = the rest), rate %].
#: Schools must confirm these against GRA's published table before the first pay run.
DEFAULT_PAYE_BANDS = [
    [58800, "0"],
    [8000, "5"],
    [10000, "10"],
    [290000, "17.5"],
    [1600000, "25"],
    [3033200, "30"],
    [None, "35"],
]


def _default_bands() -> list[list[object]]:
    return [list(b) for b in DEFAULT_PAYE_BANDS]


class PayrollSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    paye_bands = models.JSONField(default=_default_bands)
    ssnit_employee_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("5.50")
    )
    ssnit_employer_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("13.00")
    )
    tier2_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        help_text="Part of the total sent to Tier 2",
    )
    ssnit_cap_pesewas = models.PositiveBigIntegerField(
        default=6_900_000, help_text="Most basic salary SSNIT is charged on, per month"
    )
    rates_confirmed_at = models.DateTimeField(null=True, blank=True)
    rates_confirmed_by = models.UUIDField(null=True, blank=True)

    @classmethod
    def load(cls) -> PayrollSettings:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Salary(models.Model):
    staff = models.OneToOneField(StaffProfile, on_delete=models.CASCADE, related_name="salary")
    basic_pesewas = models.PositiveBigIntegerField(default=0)
    allowances = models.JSONField(
        default=list, blank=True, help_text='[{"name", "amount_pesewas", "taxable"}]'
    )
    deductions = models.JSONField(
        default=list, blank=True, help_text='[{"name", "amount_pesewas"}]'
    )
    ssnit_number = models.CharField(max_length=30, blank=True)
    tin = EncryptedTextField(blank=True, default="", help_text="Ghana Card / GRA TIN")
    on_payroll = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)


class PayRun(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Being prepared"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    month = models.DateField(unique=True, help_text="The first day of the month paid for")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    gross_pesewas = models.PositiveBigIntegerField(default=0)
    paye_pesewas = models.PositiveBigIntegerField(default=0)
    ssnit_employee_pesewas = models.PositiveBigIntegerField(default=0)
    ssnit_employer_pesewas = models.PositiveBigIntegerField(default=0)
    other_deductions_pesewas = models.PositiveBigIntegerField(default=0)
    net_pesewas = models.PositiveBigIntegerField(default=0)
    prepared_by = models.UUIDField()
    approved_by = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-month"]


class Payslip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(PayRun, on_delete=models.CASCADE, related_name="payslips")
    staff = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name="payslips")
    staff_name = models.CharField(max_length=160)
    basic_pesewas = models.PositiveBigIntegerField()
    allowances = models.JSONField(default=list)
    gross_pesewas = models.PositiveBigIntegerField()
    ssnit_employee_pesewas = models.PositiveBigIntegerField()
    ssnit_employer_pesewas = models.PositiveBigIntegerField()
    taxable_pesewas = models.PositiveBigIntegerField()
    paye_pesewas = models.PositiveBigIntegerField()
    deductions = models.JSONField(default=list)
    deductions_pesewas = models.PositiveBigIntegerField()
    net_pesewas = models.BigIntegerField()

    class Meta:
        ordering: ClassVar = ["staff_name"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["run", "staff"], name="one_payslip_each_run")
        ]
