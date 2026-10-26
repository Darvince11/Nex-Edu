"""Online tests: questions, a window to sit them, one timed attempt per pupil, marks."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.academics.models import ClassArm, Subject
from apps.students.models import Student


class Test(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    arm = models.ForeignKey(ClassArm, on_delete=models.CASCADE, related_name="online_tests")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="online_tests")
    title = models.CharField(max_length=140)
    instructions = models.TextField(max_length=2000, blank=True)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    minutes = models.PositiveSmallIntegerField(default=30, help_text="Time allowed once started")
    published = models.BooleanField(default=False, help_text="Pupils can see it")
    results_released = models.BooleanField(default=False)
    created_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-opens_at"]

    def __str__(self) -> str:
        return self.title


class Question(models.Model):
    class Kind(models.TextChoices):
        CHOICE = "choice", "One correct answer"
        TRUE_FALSE = "true_false", "True or false"
        SHORT = "short", "Short answer (marked by the teacher)"

    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveSmallIntegerField(default=0)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CHOICE)
    text = models.TextField(max_length=2000)
    options = models.JSONField(default=list, blank=True)
    answer = models.JSONField(
        null=True, blank=True, help_text="Index of the right option, or a model answer"
    )
    marks = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering: ClassVar = ["order", "pk"]


class Attempt(models.Model):
    class Status(models.TextChoices):
        STARTED = "started", "In progress"
        SUBMITTED = "submitted", "Handed in"
        MARKED = "marked", "Marked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="test_attempts")
    started_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict, blank=True)
    awarded = models.JSONField(default=dict, blank=True, help_text="Marks per question id")
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.STARTED)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["test", "student"], name="one_attempt_each")
        ]
