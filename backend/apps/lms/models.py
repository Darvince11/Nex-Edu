"""Online learning: homework set for a class and subject, pupils' work handed in
online, marks and feedback, and learning materials."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.academics.models import ClassArm, Subject
from apps.students.models import Student
from core.links import VideoLinkField


class Homework(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    arm = models.ForeignKey(ClassArm, on_delete=models.CASCADE, related_name="homework")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="homework")
    title = models.CharField(max_length=140)
    instructions = models.TextField(max_length=4000, blank=True)
    due_on = models.DateField(db_index=True)
    max_score = models.PositiveSmallIntegerField(null=True, blank=True)
    hand_in_online = models.BooleanField(default=True)
    attachment_key = models.CharField(max_length=300, blank=True)
    attachment_name = models.CharField(max_length=120, blank=True)
    video_url = VideoLinkField()
    set_by = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-due_on", "-created_at"]

    def __str__(self) -> str:
        return self.title


class Submission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="submissions")
    text = models.TextField(max_length=8000, blank=True)
    file_key = models.CharField(max_length=300, blank=True)
    file_name = models.CharField(max_length=120, blank=True)
    submitted_at = models.DateTimeField()
    late = models.BooleanField(default=False)
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback = models.CharField(max_length=1000, blank=True)
    marked_by = models.UUIDField(null=True, blank=True)
    marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["student__last_name", "student__first_name"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["homework", "student"], name="one_submission_each")
        ]


class Material(models.Model):
    """Notes, links and files a teacher shares with a class."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    arm = models.ForeignKey(ClassArm, on_delete=models.CASCADE, related_name="materials")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="materials")
    title = models.CharField(max_length=140)
    note = models.TextField(max_length=4000, blank=True)
    link = models.URLField(blank=True)
    file_key = models.CharField(max_length=300, blank=True)
    file_name = models.CharField(max_length=120, blank=True)
    shared_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]
