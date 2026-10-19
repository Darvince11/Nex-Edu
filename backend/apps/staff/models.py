from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from core.crypto import EncryptedTextField


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
