from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from django.db import models
from django.http import HttpRequest
from django.utils import timezone

from control_plane.tenancy import tenant_atomic
from core.crypto import EncryptedTextField
from core.misc import client_ip

from .models import AuditChainHead, AuditEvent

GENESIS_HASH = "0" * 64
REDACTED = "[encrypted field changed]"

_HASHED_FIELDS = (
    "seq",
    "occurred_at",
    "actor_id",
    "actor_email",
    "action",
    "target_type",
    "target_id",
    "ip",
    "user_agent",
    "request_id",
    "before",
    "after",
    "reason",
    "prev_hash",
)


def _canonical(event: AuditEvent) -> bytes:
    payload: dict[str, Any] = {}
    for name in _HASHED_FIELDS:
        value = getattr(event, name)
        if name == "occurred_at":
            value = value.isoformat()
        elif name == "actor_id" and value is not None:
            value = str(value)
        payload[name] = value
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def compute_hash(event: AuditEvent) -> str:
    return hashlib.sha256(_canonical(event)).hexdigest()


def snapshot(instance: models.Model, fields: list[str] | None = None) -> dict[str, Any]:
    """A JSON-safe copy of a model for before/after. Encrypted values are never logged."""
    data: dict[str, Any] = {}
    for field in instance._meta.concrete_fields:
        if fields and field.name not in fields:
            continue
        value = getattr(instance, field.attname)
        if isinstance(field, EncryptedTextField):
            data[field.name] = REDACTED if value else None
        else:
            data[field.name] = (
                value if isinstance(value, int | float | bool | type(None)) else str(value)
            )
    return data


def record_event(
    *,
    action: str,
    request: HttpRequest | None = None,
    actor: Any = None,
    target: models.Model | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
) -> AuditEvent:
    """Append one event to the current school's chain."""
    if actor is None and request is not None:
        actor = getattr(request, "user", None)
    actor_ok = actor is not None and getattr(actor, "is_authenticated", False)

    with tenant_atomic():
        head, _ = AuditChainHead.objects.select_for_update().get_or_create(pk=1)
        event = AuditEvent(
            seq=head.last_seq + 1,
            occurred_at=timezone.now(),
            actor_id=actor.pk if actor_ok else None,
            actor_email=getattr(actor, "email", "") if actor_ok else "",
            action=action,
            target_type=target._meta.label_lower if target is not None else "",
            target_id=str(target.pk) if target is not None else "",
            ip=client_ip(request) if request is not None else "",
            user_agent=(request.headers.get("User-Agent", "")[:300] if request is not None else ""),
            request_id=getattr(request, "request_id", "") if request is not None else "",
            before=before,
            after=after,
            reason=reason[:500],
            prev_hash=head.last_hash,
        )
        event.hash = compute_hash(event)
        event.save()
        head.last_seq = event.seq
        head.last_hash = event.hash
        head.save(update_fields=["last_seq", "last_hash"])
    return event


@dataclass
class ChainReport:
    valid: bool
    checked: int
    first_bad_seq: int | None = None
    reason: str = ""


def verify_chain(batch_size: int = 2000) -> ChainReport:
    """Recompute every hash in order and check each link."""
    expected_prev = GENESIS_HASH
    expected_seq = 1
    checked = 0
    queryset = AuditEvent.objects.order_by("seq")
    for event in queryset.iterator(chunk_size=batch_size):
        if event.seq != expected_seq:
            return ChainReport(False, checked, expected_seq, "missing event")
        if event.prev_hash != expected_prev:
            return ChainReport(False, checked, event.seq, "broken link")
        if compute_hash(event) != event.hash:
            return ChainReport(False, checked, event.seq, "contents altered")
        expected_prev = event.hash
        expected_seq += 1
        checked += 1
    head = AuditChainHead.objects.filter(pk=1).first()
    if head and (head.last_seq != checked or head.last_hash != expected_prev):
        return ChainReport(False, checked, checked + 1, "events removed from the end")
    return ChainReport(True, checked)
