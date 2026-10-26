"""Accreditation and compliance: what the school must hold or renew, and the evidence."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import ClassVar

from django.db import models

#: How soon before a due date the item shows as due and reminders start.
DUE_SOON_DAYS = 30


class Requirement(models.Model):
    class Area(models.TextChoices):
        LICENCE = "licence", "Licence and registration"
        SAFETY = "safety", "Safety and premises"
        STAFF = "staff", "Staff"
        HEALTH = "health", "Health and food"
        SAFEGUARDING = "safeguarding", "Child protection"
        DATA = "data", "Data protection"
        FINANCE = "finance", "Tax and statutory payments"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "To do"
        DONE = "done", "Done"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    area = models.CharField(max_length=12, choices=Area.choices, default=Area.OTHER)
    title = models.CharField(max_length=150)
    authority = models.CharField(max_length=120, blank=True, help_text="Who issues or inspects it")
    notes = models.TextField(max_length=2000, blank=True)
    due_on = models.DateField(null=True, blank=True, help_text="Deadline, or the next renewal")
    renew_every_months = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Leave empty if it never needs renewing"
    )
    status = models.CharField(max_length=4, choices=Status.choices, default=Status.OPEN)
    completed_on = models.DateField(null=True, blank=True)
    last_reminded_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = [models.F("due_on").asc(nulls_last=True), "title"]

    def state(self, today: dt.date) -> str:
        """done, open, due_soon or overdue. A renewable item comes due again."""
        if self.status == self.Status.DONE and not self.renew_every_months:
            return "done"
        if self.due_on and self.due_on < today:
            return "overdue"
        if self.due_on and self.due_on <= today + dt.timedelta(days=DUE_SOON_DAYS):
            return "due_soon"
        return "done" if self.status == self.Status.DONE else "open"


class Evidence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requirement = models.ForeignKey(Requirement, on_delete=models.CASCADE, related_name="evidence")
    name = models.CharField(max_length=120)
    file_key = models.CharField(max_length=300)
    size = models.PositiveIntegerField()
    uploaded_by = models.UUIDField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-uploaded_at"]
