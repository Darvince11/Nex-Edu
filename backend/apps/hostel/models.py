"""Boarding: houses, rooms and beds, who sleeps where, roll calls, and exeats
(permission to leave school and come back)."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.db.models import Q

from apps.students.models import Student


class House(models.Model):
    class Gender(models.TextChoices):
        GIRLS = "girls", "Girls"
        BOYS = "boys", "Boys"
        MIXED = "mixed", "Mixed"

    name = models.CharField(max_length=80, unique=True)
    gender = models.CharField(max_length=5, choices=Gender.choices, default=Gender.MIXED)
    warden_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return self.name


class Room(models.Model):
    house = models.ForeignKey(House, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=40)
    beds = models.PositiveSmallIntegerField(default=4)

    class Meta:
        ordering: ClassVar = ["house__name", "name"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["house", "name"], name="uniq_room_per_house")
        ]

    def __str__(self) -> str:
        return f"{self.house.name} {self.name}"


class Boarder(models.Model):
    """A pupil's bed. Ending it (``left_on``) keeps the history."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="boarding")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="boarders")
    since = models.DateField(auto_now_add=True)
    left_on = models.DateField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["student"], condition=Q(left_on__isnull=True), name="one_current_bed"
            )
        ]


class RollCall(models.Model):
    class Session(models.TextChoices):
        MORNING = "morning", "Morning"
        EVENING = "evening", "Evening"

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        EXEAT = "exeat", "On exeat"
        SICK_BAY = "sick_bay", "In the sick bay"

    house = models.ForeignKey(House, on_delete=models.CASCADE, related_name="roll_calls")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="roll_calls")
    date = models.DateField()
    session = models.CharField(max_length=8, choices=Session.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    marked_by = models.UUIDField()
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["student", "date", "session"], name="one_roll_mark_per_session"
            )
        ]


class Exeat(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Waiting for approval"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"
        OUT = "out", "Away"
        RETURNED = "returned", "Back"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="exeats")
    leaves_on = models.DateField()
    returns_on = models.DateField()
    reason = models.CharField(max_length=200)
    collected_by = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    requested_by = models.UUIDField()
    decided_by = models.UUIDField(null=True, blank=True)
    decision_note = models.CharField(max_length=200, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-leaves_on", "-created_at"]
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(returns_on__gte=models.F("leaves_on")),
                name="exeat_returns_after_leaving",
            )
        ]
