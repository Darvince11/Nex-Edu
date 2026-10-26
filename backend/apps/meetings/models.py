"""Parent meetings: a day set aside for parents to see their children's teachers,
split into short slots that parents book."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.db.models import Q

from apps.students.models import Student
from core.links import VideoLinkField


class MeetingDay(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120, help_text='e.g. "End of term parent meetings"')
    date = models.DateField()
    starts_at = models.TimeField()
    ends_at = models.TimeField()
    slot_minutes = models.PositiveSmallIntegerField(default=10)
    location = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    video_url = VideoLinkField(help_text="For meetings held online")
    is_open = models.BooleanField(default=False, help_text="Parents can book")
    created_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-date"]
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="meeting_ends_after_start"
            )
        ]

    def __str__(self) -> str:
        return self.title


class MeetingTeacher(models.Model):
    """A member of staff seeing parents on the day (``user_id`` is a control-plane user)."""

    day = models.ForeignKey(MeetingDay, on_delete=models.CASCADE, related_name="teachers")
    user_id = models.UUIDField()
    room = models.CharField(max_length=60, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["day", "user_id"], name="uniq_meeting_teacher")
        ]


class Slot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    day = models.ForeignKey(MeetingDay, on_delete=models.CASCADE, related_name="slots")
    teacher_user_id = models.UUIDField(db_index=True)
    starts_at = models.TimeField()
    ends_at = models.TimeField()
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, null=True, blank=True, related_name="meeting_slots"
    )
    booked_by = models.UUIDField(null=True, blank=True)
    booked_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(
        max_length=200, blank=True, help_text="What the parent wants to discuss"
    )

    class Meta:
        ordering: ClassVar = ["starts_at"]
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["day", "teacher_user_id", "starts_at"], name="uniq_slot_time"
            ),
            # One slot per child with each teacher on a day.
            models.UniqueConstraint(
                fields=["day", "teacher_user_id", "student"],
                condition=Q(student__isnull=False),
                name="one_booking_per_child_teacher",
            ),
        ]
