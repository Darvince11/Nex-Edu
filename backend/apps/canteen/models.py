"""The canteen: what's on sale, each pupil's wallet, and meals served on a term plan.
Money in pesewas; every wallet movement is also posted to the school's books."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.academics.models import Term
from apps.students.models import Student


class MenuItem(models.Model):
    class Kind(models.TextChoices):
        MEAL = "meal", "Meal"
        SNACK = "snack", "Snack"
        DRINK = "drink", "Drink"

    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=6, choices=Kind.choices, default=Kind.MEAL)
    price_pesewas = models.PositiveIntegerField()
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["kind", "name"]

    def __str__(self) -> str:
        return self.name


class Wallet(models.Model):
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name="canteen_wallet")
    balance_pesewas = models.IntegerField(default=0)
    daily_limit_pesewas = models.PositiveIntegerField(
        null=True, blank=True, help_text="Most the pupil may spend in a day (parents set it)"
    )
    low_balance_pesewas = models.PositiveIntegerField(default=1000)
    updated_at = models.DateTimeField(auto_now=True)


class WalletEntry(models.Model):
    class Kind(models.TextChoices):
        TOP_UP = "top_up", "Top-up"
        PURCHASE = "purchase", "Purchase"
        REFUND = "refund", "Refund"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="entries")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount_pesewas = models.IntegerField(help_text="Positive in, negative out")
    balance_after_pesewas = models.IntegerField()
    items = models.JSONField(default=list, blank=True)
    reference = models.CharField(max_length=60, blank=True)
    created_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]


class MealPlan(models.Model):
    """A pupil whose meals for a term are paid for (usually through a feeding fee)."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="meal_plans")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="+")
    note = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["student", "term"], name="one_meal_plan_per_term")
        ]


class Serving(models.Model):
    """A meal served on a plan: at most one a day."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="servings")
    date = models.DateField()
    served_by = models.UUIDField()
    served_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["student", "date"], name="one_plan_meal_a_day")
        ]
