"""AI drafting help: a log of drafts made (never their text), for the daily limit and audit."""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class DraftLog(models.Model):
    class Kind(models.TextChoices):
        REPORT_COMMENT = "report_comment", "Report-card comment"
        ANNOUNCEMENT = "announcement", "Announcement"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    user_id = models.UUIDField(db_index=True)
    ok = models.BooleanField(default=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]
