"""Developer API (optional module ``developer_api``): API keys and webhooks.

Keys: made by the proprietor, one school each, read-only, limited to scopes. The
key is shown once; only its SHA-256 is kept. ``nxk_<prefix>_<secret>``.

Webhooks: the school names an https address and the events it wants. Each
delivery is a JSON POST signed with the endpoint's secret:
``X-NexEdu-Signature: t=<unix time>,v1=<hex HMAC-SHA256 of "<t>.<body>">``.
Failed deliveries are retried (1 min, 5 min, 30 min, 2 h, 6 h) then given up.
Addresses that resolve to private, loopback or link-local networks are refused
when saved and again before every send, so a webhook can't reach Nex Edu's own
servers.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import time
from typing import Any
from urllib.parse import urlsplit

from celery import shared_task
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from control_plane.models import ApiKey, Tenant, WebhookDelivery, WebhookEndpoint
from integrations import http

logger = logging.getLogger(__name__)

MODULE = "developer_api"
SCOPES = {
    "students:read": "Pupils: names, admission numbers, classes, status",
    "classes:read": "Classes and subjects",
    "attendance:read": "Daily attendance marks",
    "finance:read": "Invoices and payments",
}
EVENTS = {
    "payment.received": "A fee payment came in (online or recorded)",
    "student.admitted": "An applicant was enrolled",
    "results.published": "A class's report cards were published",
}
RETRY_SECONDS = (60, 300, 1800, 7200, 21600)
KEY_PREFIX = "nxk_"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# --- API keys ------------------------------------------------------------------------------


def create_key(*, tenant: Tenant, user: Any, name: str, scopes: list[str]) -> tuple[ApiKey, str]:
    unknown = set(scopes) - set(SCOPES)
    if unknown or not scopes:
        raise ValidationError({"scopes": "Choose what the key may read."})
    prefix = secrets.token_hex(4)
    raw = f"{KEY_PREFIX}{prefix}_{secrets.token_urlsafe(32)}"
    key = ApiKey.objects.create(
        tenant=tenant,
        name=name.strip()[:80],
        prefix=prefix,
        key_hash=_hash(raw),
        scopes=sorted(set(scopes)),
        created_by=user,
    )
    return key, raw


def find_key(raw: str) -> ApiKey | None:
    if not raw.startswith(KEY_PREFIX):
        return None
    key = (
        ApiKey.objects.select_related("tenant")
        .filter(key_hash=_hash(raw), revoked_at__isnull=True)
        .first()
    )
    if key is None or key.tenant.status != Tenant.Status.ACTIVE:
        return None
    from control_plane.modules import is_active

    if not is_active(key.tenant, MODULE):
        return None
    ApiKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
    return key


# --- Webhooks ------------------------------------------------------------------------------


def _public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            return False
    return True


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValidationError({"url": "Use an https:// address."})
    if parts.username or parts.password:
        raise ValidationError({"url": "The address can't contain a username or password."})
    if not _public_host(parts.hostname):
        raise ValidationError({"url": "That address isn't reachable on the public internet."})


def create_webhook(
    *, tenant: Tenant, user: Any, url: str, events: list[str]
) -> tuple[WebhookEndpoint, str]:
    from core.crypto import encrypt_value

    if not events or set(events) - set(EVENTS):
        raise ValidationError({"events": "Choose which events to send."})
    check_url(url)
    secret = f"whsec_{secrets.token_urlsafe(32)}"
    endpoint = WebhookEndpoint.objects.create(
        tenant=tenant,
        url=url,
        events=sorted(set(events)),
        secret=encrypt_value(secret, tenant=tenant, context="webhook.secret"),
        created_by=user,
    )
    return endpoint, secret


def emit(event: str, data: dict[str, Any]) -> int:
    """Queue ``event`` for the current school's endpoints that asked for it. Safe to
    call anywhere: nothing happens unless the module is on and someone listens."""
    from control_plane.modules import is_active
    from control_plane.tenancy import require_tenant

    tenant = require_tenant()
    endpoints = [
        e
        for e in WebhookEndpoint.objects.filter(tenant=tenant, is_active=True)
        if event in e.events
    ]
    if not endpoints or not is_active(tenant, MODULE):
        return 0
    payload = {
        "id": f"evt_{secrets.token_hex(12)}",
        "type": event,
        "school": tenant.slug,
        "created_at": timezone.now().isoformat(),
        "data": json.loads(json.dumps(data, cls=DjangoJSONEncoder)),
    }
    for endpoint in endpoints:
        delivery = WebhookDelivery.objects.create(endpoint=endpoint, event=event, payload=payload)
        transaction.on_commit(lambda pk=delivery.pk: deliver.apply_async(args=[str(pk)]))
    return len(endpoints)


def signature(secret: str, body: bytes, at: int) -> str:
    digest = hmac.new(secret.encode(), f"{at}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={at},v1={digest}"


@shared_task(name="control_plane.deliver_webhook", bind=True, max_retries=len(RETRY_SECONDS))
def deliver(self: Any, delivery_id: str) -> str:
    from core.crypto import decrypt_value

    delivery = (
        WebhookDelivery.objects.select_related("endpoint__tenant").filter(pk=delivery_id).first()
    )
    if delivery is None or delivery.status != WebhookDelivery.Status.PENDING:
        return "skipped"
    endpoint = delivery.endpoint
    body = json.dumps(delivery.payload, separators=(",", ":")).encode()
    delivery.attempts += 1
    try:
        check_url(endpoint.url)
        secret = decrypt_value(endpoint.secret, tenant=endpoint.tenant, context="webhook.secret")
        with http.client() as c:
            response = c.post(
                endpoint.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "NexEdu-Webhooks/1",
                    "X-NexEdu-Event": delivery.event,
                    "X-NexEdu-Signature": signature(secret, body, int(time.time())),
                },
                follow_redirects=False,
            )
        delivery.response_code = response.status_code
        ok = 200 <= response.status_code < 300
        delivery.error = "" if ok else f"HTTP {response.status_code}"
    except Exception as exc:  # network, refused address, bad secret
        ok, delivery.error = False, str(exc)[:300]
    if ok:
        delivery.status, delivery.delivered_at = WebhookDelivery.Status.SENT, timezone.now()
    elif delivery.attempts > len(RETRY_SECONDS):
        delivery.status = WebhookDelivery.Status.FAILED
    delivery.save(update_fields=["status", "attempts", "response_code", "error", "delivered_at"])
    if not ok and delivery.status == WebhookDelivery.Status.PENDING:
        raise self.retry(countdown=RETRY_SECONDS[delivery.attempts - 1])
    return delivery.status
