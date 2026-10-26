"""Browser push notifications (Web Push, RFC 8030 with VAPID). No outside provider:
the browser's own push service delivers them, encrypted end to end.

A person turns it on per browser from their profile. Every in-app notification
(``apps.communication.services.notify_users``) is also pushed to their browsers,
as a short title and line with a link; the full text stays in the inbox. Push is
off unless the VAPID keys are set (``manage.py generate_vapid_keys``).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from control_plane.models import PushSubscription

logger = logging.getLogger(__name__)

MAX_BODY = 140


def enabled() -> bool:
    return bool(settings.WEB_PUSH_VAPID_PUBLIC_KEY and settings.WEB_PUSH_VAPID_PRIVATE_KEY)


def subscribe(user: Any, *, endpoint: str, p256dh: str, auth: str, user_agent: str = "") -> None:
    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={"user": user, "p256dh": p256dh, "auth": auth, "user_agent": user_agent[:200]},
    )


def unsubscribe(user: Any, endpoint: str) -> None:
    PushSubscription.objects.filter(user=user, endpoint=endpoint).delete()


def queue(user_ids: list[UUID], *, title: str, body: str, url: str = "/inbox") -> None:
    """Push to these people's browsers, in the background. No-op when push is off."""
    if not enabled() or not user_ids:
        return
    if not PushSubscription.objects.filter(user_id__in=user_ids).exists():
        return
    from core.tasks import enqueue_after_commit

    enqueue_after_commit(send_push, [str(u) for u in user_ids], title[:80], body[:MAX_BODY], url)


@shared_task(name="control_plane.send_push", acks_late=True)
def send_push(user_ids: list[str], title: str, body: str, url: str) -> int:
    from pywebpush import WebPushException, webpush

    payload = json.dumps({"title": title, "body": body, "url": url})
    sent = 0
    for sub in PushSubscription.objects.filter(user_id__in=user_ids):
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.WEB_PUSH_VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.WEB_PUSH_CONTACT},
                ttl=24 * 3600,
            )
        except WebPushException as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in (404, 410):  # the browser unsubscribed or the app was removed
                sub.delete()
            else:
                logger.warning("Push to %s failed: %s", sub.pk, code or exc)
            continue
        PushSubscription.objects.filter(pk=sub.pk).update(last_ok_at=timezone.now())
        sent += 1
    return sent
