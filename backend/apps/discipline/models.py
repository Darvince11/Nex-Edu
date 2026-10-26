"""Behaviour: incidents, what the school did about them, and confidential counselling
notes. Personal data about children: see ``apps.discipline.api.views`` for who sees what."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.students.models import Student


class Incident(models.Model):
    class Category(models.TextChoices):
        LATENESS = "lateness", "Lateness"
        DISRUPTION = "disruption", "Disrupting lessons"
        DISRESPECT = "disrespect", "Disrespect or rudeness"
        BULLYING = "bullying", "Bullying"
        FIGHTING = "fighting", "Fighting"
        DAMAGE = "damage", "Damage to property"
        DISHONESTY = "dishonesty", "Dishonesty or cheating"
        UNIFORM = "uniform", "Uniform or appearance"
        TRUANCY = "truancy", "Leaving school without permission"
        OTHER = "other", "Other"

    class Severity(models.TextChoices):
        MINOR = "minor", "Minor"
        MODERATE = "moderate", "Moderate"
        SERIOUS = "serious", "Serious"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="incidents")
    date = models.DateField()
    category = models.CharField(max_length=12, choices=Category.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MINOR)
    location = models.CharField(max_length=80, blank=True)
    description = models.TextField(max_length=2000)
    reported_by = models.UUIDField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    shared_with_parents_at = models.DateTimeField(null=True, blank=True)
    shared_summary = models.CharField(
        max_length=500, blank=True, help_text="What parents are told (not the staff notes)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-date", "-created_at"]
        indexes: ClassVar = [models.Index(fields=["student", "date"])]


class Action(models.Model):
    """What the school did: a warning, a detention, calling the parents, and so on."""

    class Kind(models.TextChoices):
        WARNING = "warning", "Warning"
        DETENTION = "detention", "Detention"
        PARENTS_MET = "parents_met", "Met or called the parents"
        DUTY = "duty", "Extra duty"
        COUNSELLING = "counselling", "Referred for counselling"
        SUSPENSION = "suspension", "Suspension"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="actions")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    date = models.DateField()
    days = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Suspension days")
    notes = models.CharField(max_length=500, blank=True)
    taken_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["date", "created_at"]


class CounsellingNote(models.Model):
    """Confidential: only people with ``discipline.counsel`` read or write these."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="counselling_notes")
    date = models.DateField()
    notes = models.TextField(max_length=4000)
    follow_up_on = models.DateField(null=True, blank=True)
    written_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-date", "-created_at"]
