"""The gate: who visited, and who may (and did) collect each pupil."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.students.models import Student
from core.crypto import EncryptedTextField


class Visit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, blank=True)
    organisation = models.CharField(max_length=120, blank=True)
    purpose = models.CharField(max_length=200)
    to_see = models.CharField(max_length=120, blank=True)
    id_number = EncryptedTextField(blank=True, default="", help_text="Ghana Card or other ID")
    badge = models.CharField(max_length=20, blank=True)
    arrived_at = models.DateTimeField(db_index=True)
    left_at = models.DateTimeField(null=True, blank=True)
    signed_in_by = models.UUIDField()

    class Meta:
        ordering: ClassVar = ["-arrived_at"]


class Collector(models.Model):
    """Someone a pupil's family says may collect the pupil from school."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="collectors")
    name = models.CharField(max_length=120)
    relationship = models.CharField(max_length=40)
    phone = models.CharField(max_length=20, blank=True)
    notes = models.CharField(max_length=200, blank=True, help_text="e.g. what they look like")
    added_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["name"]


class Pickup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="pickups")
    collector = models.ForeignKey(
        Collector, on_delete=models.SET_NULL, null=True, blank=True, related_name="pickups"
    )
    collected_by_name = models.CharField(max_length=120)
    authorised = models.BooleanField()
    reason = models.CharField(max_length=200, blank=True, help_text="Needed when not on the list")
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    recorded_by = models.UUIDField()

    class Meta:
        ordering: ClassVar = ["-at"]
