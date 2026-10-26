"""School transport: vehicles, routes and their stops, which pupils ride where, and
the driver's pick-up list for each trip."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.db.models import Q

from apps.students.models import Student


class Vehicle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=60, help_text='e.g. "Bus 1"')
    registration = models.CharField(max_length=20, blank=True, help_text="e.g. GR 1234-23")
    seats = models.PositiveSmallIntegerField(default=30)
    driver_user_id = models.UUIDField(null=True, blank=True, db_index=True)
    attendant = models.CharField(max_length=80, blank=True)
    attendant_phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return self.name


class Route(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80, unique=True, help_text='e.g. "Kasoa route"')
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="routes"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return self.name


class Stop(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stops")
    name = models.CharField(max_length=80)
    order = models.PositiveSmallIntegerField(default=0)
    pickup_at = models.TimeField(null=True, blank=True, help_text="Morning pick-up")
    drop_at = models.TimeField(null=True, blank=True, help_text="Afternoon drop-off")

    class Meta:
        ordering: ClassVar = ["order", "pickup_at"]


class Rider(models.Model):
    """A pupil who rides a route, getting on and off at a stop."""

    class Direction(models.TextChoices):
        BOTH = "both", "Both ways"
        MORNING = "morning", "Mornings only"
        AFTERNOON = "afternoon", "Afternoons only"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="bus_rides")
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="riders")
    stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="riders")
    direction = models.CharField(max_length=10, choices=Direction.choices, default=Direction.BOTH)
    since = models.DateField(auto_now_add=True)
    ended_on = models.DateField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["student"], condition=Q(ended_on__isnull=True), name="one_current_route"
            )
        ]


class TripMark(models.Model):
    """The driver's (or attendant's) mark for one pupil on one trip."""

    class Direction(models.TextChoices):
        MORNING = "morning", "Morning"
        AFTERNOON = "afternoon", "Afternoon"

    class Status(models.TextChoices):
        BOARDED = "boarded", "Got on"
        DROPPED = "dropped", "Dropped off"
        ABSENT = "absent", "Not at the stop"

    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="marks")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="bus_marks")
    date = models.DateField()
    direction = models.CharField(max_length=10, choices=Direction.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    marked_at = models.DateTimeField(auto_now=True)
    marked_by = models.UUIDField()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["student", "date", "direction"], name="one_mark_per_trip"
            )
        ]
