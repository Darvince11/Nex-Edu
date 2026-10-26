"""Accounting beyond fees: money the school spends and other money it receives, and
yearly budgets. Every transaction is also a balanced journal entry in the school's
books (``apps.finance``); a mistake is voided by posting the reverse, never deleted."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.academics.models import AcademicSession
from apps.finance.models import JournalEntry, LedgerAccount


class Transaction(models.Model):
    class Kind(models.TextChoices):
        EXPENSE = "expense", "Money spent"
        INCOME = "income", "Money received"

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer or cheque"
        MOMO = "momo", "Mobile money"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=7, choices=Kind.choices)
    date = models.DateField(db_index=True)
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="+")
    amount_pesewas = models.PositiveBigIntegerField()
    method = models.CharField(max_length=5, choices=Method.choices, default=Method.CASH)
    party = models.CharField(max_length=120, help_text="Paid to, or received from")
    reference = models.CharField(max_length=60, blank=True, help_text="Receipt or cheque number")
    description = models.CharField(max_length=300, blank=True)
    entry = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, related_name="+")
    voided_by_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    void_reason = models.CharField(max_length=200, blank=True)
    recorded_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-date", "-created_at"]


class Budget(models.Model):
    """What the school plans to spend (or receive) on an account in a school year."""

    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="+")
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name="+")
    amount_pesewas = models.PositiveBigIntegerField()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["account", "session"], name="one_budget_per_account_year"
            )
        ]
