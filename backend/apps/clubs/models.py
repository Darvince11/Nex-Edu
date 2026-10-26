"""Clubs, societies and sports teams: who leads them, who belongs, and what they do."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.db.models import Q

from apps.students.models import Student


class Club(models.Model):
    class Kind(models.TextChoices):
        CLUB = "club", "Club or society"
        SPORT = "sport", "Sports team"
        ARTS = "arts", "Music, drama or cultural group"
        UNIFORMED = "uniformed", "Uniformed group (Scouts, Guides, Cadets)"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CLUB)
    description = models.CharField(max_length=300, blank=True)
    meets = models.CharField(
        max_length=120,
        blank=True,
        help_text='When and where, e.g. "Wednesdays 2:30pm, Science lab"',
    )
    capacity = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return self.name


class Patron(models.Model):
    """A member of staff who runs the club (``user_id`` is a control-plane user)."""

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="patrons")
    user_id = models.UUIDField(db_index=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["club", "user_id"], name="uniq_club_patron")
        ]


class Membership(models.Model):
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="members")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="club_memberships")
    title = models.CharField(max_length=40, blank=True, help_text='e.g. "President", "Captain"')
    joined_on = models.DateField(auto_now_add=True)
    left_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["student__last_name", "student__first_name"]
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["club", "student"],
                condition=Q(left_on__isnull=True),
                name="one_current_membership",
            )
        ]


class Activity(models.Model):
    class Kind(models.TextChoices):
        MEETING = "meeting", "Meeting"
        PRACTICE = "practice", "Practice"
        MATCH = "match", "Match or competition"
        OUTING = "outing", "Trip or outing"
        EVENT = "event", "Event or performance"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="activities")
    title = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.MEETING)
    date = models.DateField(db_index=True)
    starts_at = models.TimeField(null=True, blank=True)
    venue = models.CharField(max_length=120, blank=True)
    opponent = models.CharField(max_length=120, blank=True)
    result = models.CharField(max_length=120, blank=True, help_text='e.g. "Won 2-1"')
    notes = models.CharField(max_length=500, blank=True)
    created_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["date", "starts_at"]
