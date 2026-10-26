"""The school stores: what's in stock, what came in and went out, requests from
staff, suppliers, and the register of equipment (assets)."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models


class Supplier(models.Model):
    name = models.CharField(max_length=120, unique=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return self.name


class Item(models.Model):
    class Category(models.TextChoices):
        STATIONERY = "stationery", "Stationery"
        CLEANING = "cleaning", "Cleaning"
        BOOKS = "books", "Exercise books and textbooks"
        UNIFORM = "uniform", "Uniforms"
        SPORTS = "sports", "Sports"
        KITCHEN = "kitchen", "Kitchen"
        SCIENCE = "science", "Science and ICT"
        OTHER = "other", "Other"

    name = models.CharField(max_length=120, unique=True)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.OTHER)
    unit = models.CharField(max_length=20, default="pieces", help_text='e.g. "reams", "boxes"')
    reorder_level = models.PositiveIntegerField(
        default=0, help_text="Warn when stock falls this low"
    )
    in_stock = models.IntegerField(default=0)
    location = models.CharField(max_length=60, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def low(self) -> bool:
        return self.in_stock <= self.reorder_level


class Movement(models.Model):
    class Kind(models.TextChoices):
        RECEIVED = "received", "Received"
        ISSUED = "issued", "Issued"
        ADJUSTED = "adjusted", "Stock count adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    quantity = models.IntegerField(help_text="Positive in, negative out")
    stock_after = models.IntegerField()
    date = models.DateField()
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    unit_cost_pesewas = models.PositiveIntegerField(null=True, blank=True)
    issued_to = models.CharField(
        max_length=120, blank=True, help_text="Person, class or department"
    )
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-date", "-created_at"]


class Request(models.Model):
    """A member of staff asking the stores for something."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting"
        ISSUED = "issued", "Issued"
        DECLINED = "declined", "Declined"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="requests")
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=200, blank=True)
    requested_by = models.UUIDField(db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_by = models.UUIDField(null=True, blank=True)
    decision_note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]


class Asset(models.Model):
    """Equipment the school owns and keeps track of: projectors, laptops, furniture."""

    class Condition(models.TextChoices):
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        POOR = "poor", "Needs repair"
        RETIRED = "retired", "Written off"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tag = models.CharField(max_length=30, unique=True, help_text="The number on the label")
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=60, blank=True)
    location = models.CharField(max_length=80, blank=True)
    assigned_to = models.CharField(max_length=120, blank=True)
    condition = models.CharField(max_length=8, choices=Condition.choices, default=Condition.GOOD)
    purchased_on = models.DateField(null=True, blank=True)
    cost_pesewas = models.PositiveIntegerField(null=True, blank=True)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notes = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["tag"]
