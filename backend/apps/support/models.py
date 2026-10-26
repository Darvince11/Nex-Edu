"""Learning support: a plan for a pupil with additional needs, its goals, the
adjustments teachers make, and progress notes. Health and needs information is
sensitive personal data (Act 843): summaries and notes are encrypted."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.students.models import Student
from core.crypto import EncryptedTextField

NEEDS = [
    ("learning", "Learning difficulty (e.g. dyslexia)"),
    ("hearing", "Hearing"),
    ("vision", "Sight"),
    ("physical", "Physical or mobility"),
    ("speech", "Speech and language"),
    ("emotional", "Social, emotional or behavioural"),
    ("attention", "Attention (e.g. ADHD)"),
    ("autism", "Autism"),
    ("gifted", "Gifted and talented"),
    ("other", "Other"),
]


class Plan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="support_plans")
    needs = models.JSONField(default=list)
    summary = EncryptedTextField(
        blank=True, default="", help_text="Confidential: staff who run the plan"
    )
    goals = models.JSONField(default=list, help_text='[{"goal", "measure", "status"}]')
    adjustments = models.TextField(
        max_length=1000, blank=True, help_text="What every teacher should do"
    )
    extra_time_percent = models.PositiveSmallIntegerField(
        default=0, help_text="Extra time in tests"
    )
    review_on = models.DateField(null=True, blank=True)
    shared_with_parents = models.BooleanField(default=False)
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar = ["student__last_name", "student__first_name"]


class Note(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="notes")
    date = models.DateField()
    text = EncryptedTextField()
    written_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-date", "-created_at"]
