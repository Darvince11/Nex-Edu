"""The school library: books, the copies on the shelves, and who has borrowed them."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.db.models import Q

from apps.academics.models import ClassLevel, Subject
from apps.students.models import Student


class LibrarySettings(models.Model):
    """One row per school: how long loans last and how many books a borrower may hold."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    pupil_loan_days = models.PositiveSmallIntegerField(default=14)
    staff_loan_days = models.PositiveSmallIntegerField(default=28)
    pupil_limit = models.PositiveSmallIntegerField(default=2)
    staff_limit = models.PositiveSmallIntegerField(default=5)
    max_renewals = models.PositiveSmallIntegerField(default=2)

    @classmethod
    def load(cls) -> LibrarySettings:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Book(models.Model):
    """A title in the catalogue. Each physical copy is a ``Copy``."""

    class Category(models.TextChoices):
        READER = "reader", "Reader / storybook"
        TEXTBOOK = "textbook", "Textbook"
        REFERENCE = "reference", "Reference"
        FICTION = "fiction", "Fiction"
        NON_FICTION = "non_fiction", "Non-fiction"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=160, blank=True)
    isbn = models.CharField(max_length=20, blank=True, db_index=True)
    publisher = models.CharField(max_length=120, blank=True)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.OTHER)
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    level = models.ForeignKey(
        ClassLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The class the book suits, if any",
    )
    shelf = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["title"]
        indexes: ClassVar = [models.Index(fields=["title"])]

    def __str__(self) -> str:
        return self.title


class Copy(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "On the shelf"
        ON_LOAN = "on_loan", "On loan"
        LOST = "lost", "Lost"
        WITHDRAWN = "withdrawn", "Withdrawn"

    class Condition(models.TextChoices):
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        POOR = "poor", "Poor"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="copies")
    accession_number = models.CharField(max_length=30, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE)
    condition = models.CharField(max_length=5, choices=Condition.choices, default=Condition.GOOD)
    added_on = models.DateField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["accession_number"]

    def __str__(self) -> str:
        return f"{self.accession_number} ({self.book.title})"


class Loan(models.Model):
    """A copy lent to a pupil or a member of staff."""

    class Outcome(models.TextChoices):
        OPEN = "open", "On loan"
        RETURNED = "returned", "Returned"
        LOST = "lost", "Lost"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    copy = models.ForeignKey(Copy, on_delete=models.PROTECT, related_name="loans")
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, null=True, blank=True, related_name="library_loans"
    )
    staff_user_id = models.UUIDField(null=True, blank=True, db_index=True)
    borrowed_on = models.DateField()
    due_on = models.DateField(db_index=True)
    returned_on = models.DateField(null=True, blank=True)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.OPEN)
    renewals = models.PositiveSmallIntegerField(default=0)
    issued_by = models.UUIDField()
    closed_by = models.UUIDField(null=True, blank=True)
    reminded_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-borrowed_on", "-created_at"]
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["copy"], condition=Q(outcome="open"), name="one_open_loan_per_copy"
            ),
            models.CheckConstraint(
                condition=(
                    Q(student__isnull=False, staff_user_id__isnull=True)
                    | Q(student__isnull=True, staff_user_id__isnull=False)
                ),
                name="loan_has_one_borrower",
            ),
        ]
