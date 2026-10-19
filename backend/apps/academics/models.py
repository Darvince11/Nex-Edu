"""Academic structure for a Ghanaian basic school.

Kindergarten (KG 1-2) → Primary (Basic 1-6) → Junior High (JHS 1-3), an academic
year ("2026/2027") of three terms, subjects, the teachers assigned to each class
and subject, and the timetable. Senior High is out of scope.
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Section(models.TextChoices):
    KINDERGARTEN = "kg", "Kindergarten"
    LOWER_PRIMARY = "lower_primary", "Lower primary (Basic 1-3)"
    UPPER_PRIMARY = "upper_primary", "Upper primary (Basic 4-6)"
    JHS = "jhs", "Junior High School"


class ClassLevel(models.Model):
    name = models.CharField(max_length=40, unique=True)  # e.g. "JHS 1"
    section = models.CharField(max_length=20, choices=Section.choices)
    order = models.PositiveSmallIntegerField(unique=True)
    is_active = models.BooleanField(default=True, help_text="Off if the school doesn't run it")

    class Meta:
        ordering: ClassVar = ["order"]

    def __str__(self) -> str:
        return self.name


class ClassArm(models.Model):
    """A stream within a level, e.g. "JHS 1 A"."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="arms")
    name = models.CharField(max_length=20, default="A")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["level", "name"], name="uniq_arm_per_level")
        ]
        ordering: ClassVar = ["level__order", "name"]

    def __str__(self) -> str:
        return f"{self.level.name} {self.name}"


class AcademicSession(models.Model):
    name = models.CharField(max_length=20, unique=True)  # "2026/2027"
    starts_on = models.DateField()
    ends_on = models.DateField()
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-starts_on"]
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["is_current"], condition=Q(is_current=True), name="one_current_session"
            ),
            models.CheckConstraint(
                condition=Q(ends_on__gt=models.F("starts_on")), name="session_dates_ordered"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Term(models.Model):
    class Number(models.IntegerChoices):
        FIRST = 1, "First term"
        SECOND = 2, "Second term"
        THIRD = 3, "Third term"

    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name="terms")
    number = models.PositiveSmallIntegerField(choices=Number.choices)
    starts_on = models.DateField()
    ends_on = models.DateField()
    next_term_begins = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-session__starts_on", "number"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["session", "number"], name="uniq_term_in_session"),
            models.UniqueConstraint(
                fields=["is_current"], condition=Q(is_current=True), name="one_current_term"
            ),
            models.CheckConstraint(
                condition=Q(ends_on__gt=models.F("starts_on")), name="term_dates_ordered"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_number_display()} {self.session.name}"

    def clean(self) -> None:
        if self.session_id and self.starts_on and self.ends_on:
            session = self.session
            if self.starts_on < session.starts_on or self.ends_on > session.ends_on:
                raise ValidationError("Term dates must fall within the session.")


class Subject(models.Model):
    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(max_length=12, unique=True)
    sections = models.JSONField(
        default=list, blank=True, help_text="Sections that offer this subject; empty means all"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return self.name


class TeachingAssignment(models.Model):
    """Which staff member teaches which subject to which class arm.

    ``subject`` empty means the form-teacher role for the arm (register, comments).
    ``teacher_user_id`` refers to a control-plane user. Cross-database foreign
    keys are impossible, so it is stored as a plain UUID.
    """

    teacher_user_id = models.UUIDField(db_index=True)
    arm = models.ForeignKey(ClassArm, on_delete=models.CASCADE, related_name="assignments")
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, null=True, blank=True, related_name="assignments"
    )
    is_form_teacher = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["teacher_user_id", "arm", "subject"], name="uniq_teaching_assignment"
            )
        ]


class Period(models.Model):
    """One timetable slot: a subject taught to an arm at a time on a weekday."""

    class Weekday(models.IntegerChoices):
        MONDAY = 1
        TUESDAY = 2
        WEDNESDAY = 3
        THURSDAY = 4
        FRIDAY = 5
        SATURDAY = 6

    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="periods")
    arm = models.ForeignKey(ClassArm, on_delete=models.CASCADE, related_name="periods")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="periods")
    teacher_user_id = models.UUIDField(null=True, blank=True, db_index=True)
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    starts_at = models.TimeField()
    ends_at = models.TimeField()
    room = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering: ClassVar = ["weekday", "starts_at"]
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="period_times_ordered"
            )
        ]
