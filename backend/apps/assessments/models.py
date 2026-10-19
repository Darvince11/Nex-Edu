"""Continuous assessment, exams, grading and report cards."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import ClassVar

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.academics.models import ClassArm, Section, Subject, Term
from apps.students.models import Student


class GradeBand(models.Model):
    """One row of a grading key, e.g. BECE grade 1 = 80-100 "Highest".

    ``section`` empty means the default key (NaCCA proficiency levels for KG and
    primary); a section-specific key (BECE 1-9 for JHS) takes precedence.
    """

    section = models.CharField(max_length=20, choices=Section.choices, blank=True)
    grade = models.CharField(max_length=4)
    min_score = models.DecimalField(max_digits=5, decimal_places=2)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    remark = models.CharField(max_length=40)
    points = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering: ClassVar = ["section", "-min_score"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["section", "grade"], name="uniq_grade_per_section")
        ]


class AssessmentComponent(models.Model):
    """A scored part of each subject, e.g. "Class score" out of 30, "Exam" out of 70.

    Active components must add up to 100.
    """

    name = models.CharField(max_length=40, unique=True)
    code = models.CharField(max_length=10, unique=True)
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("1")), MaxValueValidator(Decimal("100"))],
    )
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["order", "name"]

    def __str__(self) -> str:
        return f"{self.name} (/{self.max_score})"


class Score(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="scores")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="scores")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="scores")
    component = models.ForeignKey(
        AssessmentComponent, on_delete=models.PROTECT, related_name="scores"
    )
    score = models.DecimalField(max_digits=5, decimal_places=2)
    entered_by = models.UUIDField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["student", "subject", "term", "component"], name="uniq_score"
            ),
            models.CheckConstraint(condition=models.Q(score__gte=0), name="score_not_negative"),
        ]
        indexes: ClassVar = [models.Index(fields=["term", "subject"])]


class ReportCard(models.Model):
    """A student's results for one term, frozen when computed.

    ``lines`` holds one entry per subject: component scores, total, grade,
    remark, subject position, and the class's highest/lowest/average.
    Once published, parents can see it and the underlying scores are locked.
    """

    class Status(models.TextChoices):
        DRAFT = "draft"
        PUBLISHED = "published"
        WITHHELD = "withheld"  # e.g. pending fees; visible to staff only

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="report_cards")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="report_cards")
    arm = models.ForeignKey(ClassArm, on_delete=models.PROTECT, related_name="report_cards")
    lines = models.JSONField(default=list)
    total_score = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    average = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    position = models.PositiveSmallIntegerField(null=True, blank=True)
    aggregate = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="JHS only: 4 core + best 2 other subjects (BECE style)"
    )
    class_size = models.PositiveSmallIntegerField(default=0)
    days_present = models.PositiveSmallIntegerField(default=0)
    days_open = models.PositiveSmallIntegerField(default=0)
    form_teacher_comment = models.CharField(max_length=500, blank=True)
    principal_comment = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    computed_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    pdf_path = models.CharField(max_length=300, blank=True)
    needs_regeneration = models.BooleanField(default=False)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["student", "term"], name="one_report_per_term")
        ]
        indexes: ClassVar = [models.Index(fields=["arm", "term", "status"])]
