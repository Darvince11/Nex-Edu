"""Append-only, hash-chained audit trail. One chain per school database.

Every event stores the hash of the previous event, so editing or deleting any
row breaks the chain from that point on and ``verify_chain`` reports it.
Rows are also streamed to an S3 bucket with Object Lock in a separate account.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models


class AppendOnlyError(RuntimeError):
    pass


class AppendOnlyQuerySet(models.QuerySet["AuditEvent"]):
    def update(self, **kwargs: Any) -> int:
        raise AppendOnlyError("Audit events cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AppendOnlyError("Audit events cannot be deleted.")


class AuditEvent(models.Model):
    seq = models.PositiveBigIntegerField(unique=True)
    occurred_at = models.DateTimeField(db_index=True)
    actor_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_email = models.CharField(max_length=254, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=64, blank=True, db_index=True)
    ip = models.CharField(max_length=45, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering: ClassVar = ["-seq"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AppendOnlyError("Audit events cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise AppendOnlyError("Audit events cannot be deleted.")

    @property
    def created_at(self) -> Any:
        return self.occurred_at


class AuditChainHead(models.Model):
    """Single row that serialises appends and tracks export progress."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    last_seq = models.PositiveBigIntegerField(default=0)
    last_hash = models.CharField(max_length=64, default="0" * 64)
    exported_seq = models.PositiveBigIntegerField(default=0)
