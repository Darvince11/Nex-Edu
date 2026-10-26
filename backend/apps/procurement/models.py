"""Buying for the school: purchase requests, approvals, purchase orders to suppliers,
goods received, and paying the supplier. Money in pesewas."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.finance.models import LedgerAccount
from apps.inventory.models import Supplier


class ProcurementSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    proprietor_above_pesewas = models.PositiveBigIntegerField(
        default=500_000, help_text="Requests above this also need the proprietor's approval"
    )

    @classmethod
    def load(cls) -> ProcurementSettings:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Requisition(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Waiting for the head teacher"
        HEAD_APPROVED = "head_approved", "Waiting for the proprietor"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Not approved"
        ORDERED = "ordered", "Ordered"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=20, unique=True)
    purpose = models.CharField(max_length=200)
    lines = models.JSONField(help_text='[{"description", "item", "quantity", "unit_cost_pesewas"}]')
    total_pesewas = models.PositiveBigIntegerField()
    needed_by = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.SUBMITTED)
    requested_by = models.UUIDField(db_index=True)
    head_approved_by = models.UUIDField(null=True, blank=True)
    final_approved_by = models.UUIDField(null=True, blank=True)
    decision_note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        ISSUED = "issued", "Sent to supplier"
        RECEIVED = "received", "Goods received"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=20, unique=True)
    requisition = models.OneToOneField(Requisition, on_delete=models.PROTECT, related_name="order")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="orders")
    account = models.ForeignKey(
        LedgerAccount, on_delete=models.PROTECT, related_name="+", help_text="What it's spent on"
    )
    lines = models.JSONField()
    total_pesewas = models.PositiveBigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED)
    issued_by = models.UUIDField()
    received_on = models.DateField(null=True, blank=True)
    received_note = models.CharField(max_length=200, blank=True)
    invoice_reference = models.CharField(max_length=60, blank=True)
    paid_on = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]
