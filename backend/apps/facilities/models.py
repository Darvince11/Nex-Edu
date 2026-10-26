"""Facilities: the school's rooms and spaces, who has booked them, and repairs."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.db.models import Q


class Room(models.Model):
    class Kind(models.TextChoices):
        CLASSROOM = "classroom", "Classroom"
        HALL = "hall", "Hall"
        LAB = "lab", "Laboratory or ICT lab"
        FIELD = "field", "Field or court"
        OFFICE = "office", "Office"
        OTHER = "other", "Other"

    name = models.CharField(max_length=80, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CLASSROOM)
    capacity = models.PositiveSmallIntegerField(null=True, blank=True)
    bookable = models.BooleanField(default=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return self.name


class Booking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="bookings")
    date = models.DateField(db_index=True)
    starts_at = models.TimeField()
    ends_at = models.TimeField()
    purpose = models.CharField(max_length=120)
    booked_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["date", "starts_at"]
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="booking_ends_after_start"
            )
        ]


class Repair(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Can wait"
        NORMAL = "normal", "Normal"
        URGENT = "urgent", "Urgent (safety)"

    class Status(models.TextChoices):
        REPORTED = "reported", "Reported"
        IN_PROGRESS = "in_progress", "Being fixed"
        DONE = "done", "Fixed"
        WONT_FIX = "wont_fix", "Won't be fixed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True, related_name="repairs"
    )
    where = models.CharField(max_length=120, blank=True, help_text="If not a listed room")
    title = models.CharField(max_length=120)
    details = models.CharField(max_length=1000, blank=True)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REPORTED)
    reported_by = models.UUIDField()
    assigned_to = models.CharField(max_length=120, blank=True, help_text="Who is fixing it")
    cost_pesewas = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]
