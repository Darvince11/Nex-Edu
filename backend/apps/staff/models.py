from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from core.crypto import EncryptedTextField


class Department(models.Model):
    """A group of staff (e.g. "JHS Science", "Administration"), with an optional head."""

    name = models.CharField(max_length=80, unique=True)
    head = models.ForeignKey(
        "StaffProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="heads"
    )

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return self.name


class StaffProfile(models.Model):
    """HR record for a member of staff. Login and role live in the control plane."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(null=True, blank=True, unique=True)
    staff_number = models.CharField(max_length=30, unique=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    gender = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    job_title = models.CharField(max_length=80, blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="staff"
    )
    qualification = models.CharField(max_length=120, blank=True)
    employment_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # Payroll details: encrypted under the school's key.
    bank_name = models.CharField(max_length=80, blank=True)
    bank_account_name = models.CharField(max_length=120, blank=True)
    bank_account_number = EncryptedTextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar = ["last_name", "first_name"]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"


class StaffAttendance(models.Model):
    """One member of staff on one day, marked by the head teacher or administrator."""

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        LATE = "late", "Late"
        ABSENT = "absent", "Absent"
        ON_LEAVE = "on_leave", "On leave"
        EXCUSED = "excused", "Excused"

    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    time_in = models.TimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.UUIDField()
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["staff", "date"], name="one_staff_mark_per_day")
        ]
        indexes: ClassVar = [models.Index(fields=["date"])]


class LeaveRequest(models.Model):
    """A member of staff asks for time off; a school leader approves or rejects it."""

    class Kind(models.TextChoices):
        ANNUAL = "annual", "Annual leave"
        SICK = "sick", "Sick leave"
        MATERNITY = "maternity", "Maternity leave"
        PATERNITY = "paternity", "Paternity leave"
        STUDY = "study", "Study leave"
        COMPASSIONATE = "compassionate", "Compassionate leave"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name="leave")
    kind = models.CharField(max_length=15, choices=Kind.choices)
    start = models.DateField()
    end = models.DateField()
    days = models.PositiveSmallIntegerField(help_text="Working days (Monday to Friday)")
    reason = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_by = models.UUIDField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-start", "-created_at"]
        indexes: ClassVar = [models.Index(fields=["status", "start"])]
