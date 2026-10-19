from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.academics.models import AcademicSession, ClassLevel


class Application(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted"
        UNDER_REVIEW = "under_review"
        OFFERED = "offered"
        REJECTED = "rejected"
        ENROLLED = "enrolled"
        WITHDRAWN = "withdrawn"

    class Source(models.TextChoices):
        ONLINE = "online"
        OFFICE = "office"

    #: Allowed status changes. Anything else is refused.
    TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        Status.SUBMITTED: {Status.UNDER_REVIEW, Status.OFFERED, Status.REJECTED, Status.WITHDRAWN},
        Status.UNDER_REVIEW: {Status.OFFERED, Status.REJECTED, Status.WITHDRAWN},
        Status.OFFERED: {Status.ENROLLED, Status.WITHDRAWN, Status.REJECTED},
        Status.REJECTED: set(),
        Status.ENROLLED: set(),
        Status.WITHDRAWN: set(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=20, unique=True)
    session = models.ForeignKey(
        AcademicSession, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    desired_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="+")
    first_name = models.CharField(max_length=80)
    middle_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10)
    previous_school = models.CharField(max_length=160, blank=True)
    guardian_name = models.CharField(max_length=160)
    guardian_phone = models.CharField(max_length=20)
    guardian_email = models.EmailField(blank=True)
    guardian_relationship = models.CharField(max_length=30, default="parent")
    address = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.OFFICE)
    review_notes = models.TextField(blank=True)
    entrance_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    student_id = models.UUIDField(null=True, blank=True, help_text="Set once enrolled")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return f"{self.reference}: {self.first_name} {self.last_name}"
