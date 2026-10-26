"""Alumni and fundraising: past pupils who agreed to keep in touch, and gifts."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.students.models import Student


class Alumnus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.OneToOneField(
        Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="alumnus"
    )
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    class_of = models.PositiveSmallIntegerField(help_text="Year they left")
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    occupation = models.CharField(max_length=120, blank=True)
    lives_in = models.CharField(max_length=120, blank=True)
    may_contact = models.BooleanField(
        default=False, help_text="They agreed to hear from the school"
    )
    consent_recorded_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-class_of", "last_name", "first_name"]

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Gift(models.Model):
    class Kind(models.TextChoices):
        PLEDGE = "pledge", "Pledged"
        RECEIVED = "received", "Received"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alumnus = models.ForeignKey(
        Alumnus, on_delete=models.SET_NULL, null=True, blank=True, related_name="gifts"
    )
    donor = models.CharField(max_length=120, help_text="Who gave (an old pupil, a company, a PTA)")
    amount_pesewas = models.PositiveBigIntegerField()
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.RECEIVED)
    date = models.DateField()
    purpose = models.CharField(max_length=200, blank=True, help_text='e.g. "New library roof"')
    in_books = models.BooleanField(default=False, help_text="Recorded as income in Accounting")
    recorded_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-date", "-created_at"]
