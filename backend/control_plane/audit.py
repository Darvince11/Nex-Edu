"""Platform audit log: who did what across the platform (linking logins, granting
platform staff, and later tenant lifecycle and support access).

Same hash-chain design as the per-school log in ``core.audit``, but stored in the
control-plane database because these actions aren't owned by any one school.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import models, transaction
from django.http import HttpRequest
from django.utils import timezone

from core.audit.services import GENESIS_HASH, ChainReport
from core.misc import client_ip

from .models import PlatformAuditEvent, PlatformAuditHead, Tenant

_HASHED_FIELDS = (
    "seq",
    "occurred_at",
    "actor_id",
    "actor_email",
    "action",
    "tenant_id",
    "target_type",
    "target_id",
    "ip",
    "request_id",
    "data",
    "reason",
    "prev_hash",
)


def compute_hash(event: PlatformAuditEvent) -> str:
    payload: dict[str, Any] = {}
    for name in _HASHED_FIELDS:
        value = getattr(event, name)
        if name == "occurred_at":
            value = value.isoformat()
        elif name in ("actor_id", "tenant_id") and value is not None:
            value = str(value)
        payload[name] = value
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def record_platform_event(
    *,
    action: str,
    request: HttpRequest | None = None,
    actor: Any = None,
    tenant: Tenant | None = None,
    target: models.Model | None = None,
    data: dict[str, Any] | None = None,
    reason: str = "",
) -> PlatformAuditEvent:
    if actor is None and request is not None:
        actor = getattr(request, "user", None)
    actor_ok = actor is not None and getattr(actor, "is_authenticated", False)

    with transaction.atomic():
        head, _ = PlatformAuditHead.objects.select_for_update().get_or_create(pk=1)
        event = PlatformAuditEvent(
            seq=head.last_seq + 1,
            occurred_at=timezone.now(),
            actor_id=actor.pk if actor_ok else None,
            actor_email=getattr(actor, "email", "") if actor_ok else "",
            action=action,
            tenant_id=tenant.pk if tenant is not None else None,
            target_type=target._meta.label_lower if target is not None else "",
            target_id=str(target.pk) if target is not None else "",
            ip=client_ip(request) if request is not None else "",
            request_id=getattr(request, "request_id", "") if request is not None else "",
            data=data,
            reason=reason[:500],
            prev_hash=head.last_hash,
        )
        event.hash = compute_hash(event)
        event.save()
        head.last_seq = event.seq
        head.last_hash = event.hash
        head.save(update_fields=["last_seq", "last_hash"])
    return event


def verify_platform_chain(batch_size: int = 2000) -> ChainReport:
    expected_prev = GENESIS_HASH
    expected_seq = 1
    checked = 0
    for event in PlatformAuditEvent.objects.order_by("seq").iterator(chunk_size=batch_size):
        if event.seq != expected_seq:
            return ChainReport(False, checked, expected_seq, "missing event")
        if event.prev_hash != expected_prev:
            return ChainReport(False, checked, event.seq, "broken link")
        if compute_hash(event) != event.hash:
            return ChainReport(False, checked, event.seq, "contents altered")
        expected_prev = event.hash
        expected_seq += 1
        checked += 1
    head = PlatformAuditHead.objects.filter(pk=1).first()
    if head and (head.last_seq != checked or head.last_hash != expected_prev):
        return ChainReport(False, checked, checked + 1, "events removed from the end")
    return ChainReport(True, checked)
