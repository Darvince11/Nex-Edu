from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.academics.models import ClassArm, Term
from apps.students.models import Student


class AttendanceRecord(models.Model):
    """A student's status for one school day.

    Registers can be taken offline on a phone and synced later, so each record
    keeps the client-side time it was taken. When two devices disagree, the
    later observation wins and the conflict is reported back.
    """

    class Status(models.TextChoices):
        PRESENT = "present"
        ABSENT = "absent"
        LATE = "late"
        EXCUSED = "excused"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance")
    arm = models.ForeignKey(ClassArm, on_delete=models.PROTECT, related_name="+")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, null=True, related_name="+")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.UUIDField()
    recorded_at = models.DateTimeField(help_text="When the teacher took it (client clock)")
    synced_at = models.DateTimeField(auto_now=True)
    batch_id = models.UUIDField(null=True, blank=True, db_index=True)
    parent_notified = models.BooleanField(default=False)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["student", "date"], name="one_record_per_student_day")
        ]
        indexes: ClassVar = [
            models.Index(fields=["arm", "date"]),
            models.Index(fields=["term", "student"]),
        ]


class SyncedBatch(models.Model):
    """Batches already applied, so a retried offline upload is a no-op."""

    id = models.UUIDField(primary_key=True)
    received_at = models.DateTimeField(auto_now_add=True)
    result = models.JSONField(default=dict)
