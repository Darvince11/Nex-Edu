"""The sick bay: each time a pupil is seen, what was wrong, what was done, and how
it ended. Health details are encrypted under the school's own key."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.students.models import Student
from core.crypto import EncryptedTextField


class Visit(models.Model):
    class Outcome(models.TextChoices):
        RETURNED = "returned", "Back to class"
        RESTED = "rested", "Rested, then back to class"
        SENT_HOME = "sent_home", "Sent home"
        COLLECTED = "collected", "Collected by a parent"
        REFERRED = "referred", "Referred to a clinic or hospital"

    #: Outcomes the parents are always told about.
    TELL_PARENTS: ClassVar = {Outcome.SENT_HOME, Outcome.COLLECTED, Outcome.REFERRED}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="clinic_visits")
    arrived_at = models.DateTimeField(db_index=True)
    left_at = models.DateTimeField(null=True, blank=True)
    complaint = EncryptedTextField()
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    treatment = EncryptedTextField(blank=True, default="")
    medication = EncryptedTextField(
        blank=True, default="", help_text="What was given, and how much"
    )
    outcome = models.CharField(max_length=10, choices=Outcome.choices, blank=True)
    seen_by = models.UUIDField()
    parents_told_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-arrived_at"]

    @property
    def in_sick_bay(self) -> bool:
        return not self.outcome
