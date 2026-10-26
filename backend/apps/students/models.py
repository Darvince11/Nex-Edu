from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.academics.models import ClassArm
from core.crypto import EncryptedTextField


class Student(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        GRADUATED = "graduated"
        WITHDRAWN = "withdrawn"
        SUSPENDED = "suspended"

    class Gender(models.TextChoices):
        FEMALE = "female"
        MALE = "male"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admission_number = models.CharField(max_length=30, unique=True)
    first_name = models.CharField(max_length=80)
    middle_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=Gender.choices)
    arm = models.ForeignKey(
        ClassArm, on_delete=models.PROTECT, null=True, blank=True, related_name="students"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    admitted_on = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    hometown = models.CharField(max_length=80, blank=True)
    region = models.CharField(max_length=40, blank=True)
    #: Control-plane user id for the student's own login, if any.
    user_id = models.UUIDField(null=True, blank=True, unique=True)

    # Sensitive: encrypted under the school's data key.
    medical_notes = EncryptedTextField(blank=True, default="")
    national_id = EncryptedTextField(blank=True, default="", help_text="Ghana Card number")
    national_id_bidx = models.CharField(max_length=64, blank=True, db_index=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes: ClassVar = [
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["arm", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} ({self.admission_number})"

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.last_name, self.first_name, self.middle_name) if p)


class StudentGuardian(models.Model):
    """A parent or guardian contact. A login (control-plane user) is optional:
    many parents are reached only by phone, through SMS and WhatsApp."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="guardians")
    guardian_user_id = models.UUIDField(null=True, blank=True, db_index=True)
    full_name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    relationship = models.CharField(max_length=30, default="parent")
    is_primary = models.BooleanField(default=False)
    receives_sms = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["student", "guardian_user_id"], name="uniq_guardian")
        ]


class PromotionRun(models.Model):
    """One end-of-year promotion: who moved where, kept for reference."""

    session = models.ForeignKey(
        "academics.AcademicSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    run_by = models.UUIDField()
    run_at = models.DateTimeField(auto_now_add=True)
    summary = models.JSONField(
        default=dict
    )  # {"promoted": n, "repeated": n, "graduated": n, "left": n}
    moves = models.JSONField(default=list)  # [{"student", "name", "action", "from", "to"}]

    class Meta:
        ordering: ClassVar = ["-run_at"]
