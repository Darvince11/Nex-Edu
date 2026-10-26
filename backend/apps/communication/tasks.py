from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from core.tasks import TenantTask
from integrations.messaging import DeliveryError, sender_for

from .models import Channel, Delivery, MessagingSettings

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


@shared_task(base=TenantTask, name="communication.send_deliveries", bind=True, max_retries=3)
def send_deliveries(self: TenantTask, delivery_ids: list[str]) -> dict[str, int]:
    from control_plane.modules import is_active
    from control_plane.subscriptions import sms_allowance, use_bought_sms
    from control_plane.tenancy import require_tenant

    from .services import sms_sent_this_month

    settings_row = MessagingSettings.load()
    # The monthly allowance Nex Edu includes, then SMS the school bought.
    allowance = sms_allowance(require_tenant())
    from_allowance = max(allowance["monthly"] - sms_sent_this_month(), 0)
    sms_budget = from_allowance + allowance["bought"]
    sms_sent = 0
    # Text messages need the SMS module; email and in-app messages are core.
    sms_on = is_active(require_tenant(), "sms")
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    retry_ids: list[str] = []

    for delivery in Delivery.objects.filter(pk__in=delivery_ids, status=Delivery.Status.QUEUED):
        if delivery.channel in (Channel.SMS, Channel.WHATSAPP) and not sms_on:
            delivery.status = Delivery.Status.SKIPPED
            delivery.error = "SMS is switched off for this school"
            delivery.save(update_fields=["status", "error"])
            counts["skipped"] += 1
            continue
        if delivery.channel == Channel.SMS:
            if sms_budget <= 0:
                delivery.status = Delivery.Status.SKIPPED
                delivery.error = "No SMS left this month: buy an SMS bundle"
                delivery.save(update_fields=["status", "error"])
                counts["skipped"] += 1
                continue
            sms_budget -= 1
        if delivery.channel == Channel.WHATSAPP and not settings_row.whatsapp_enabled:
            delivery.status = Delivery.Status.SKIPPED
            delivery.error = "WhatsApp is not enabled for this school"
            delivery.save(update_fields=["status", "error"])
            counts["skipped"] += 1
            continue

        sender = sender_for(delivery.channel)
        delivery.attempts += 1
        try:
            delivery.provider_message_id = sender.send(
                to=delivery.to,
                body=delivery.body,
                subject=delivery.subject,
                sender_id=settings_row.sms_sender_id,
            )
        except (DeliveryError, OSError) as exc:
            delivery.error = str(exc)[:300]
            if delivery.attempts >= MAX_ATTEMPTS:
                delivery.status = Delivery.Status.FAILED
                counts["failed"] += 1
            else:
                retry_ids.append(str(delivery.pk))
        else:
            delivery.status = Delivery.Status.SENT
            delivery.sent_at = timezone.now()
            counts["sent"] += 1
            sms_sent += delivery.channel == Channel.SMS
        delivery.provider = sender.name
        delivery.save(
            update_fields=[
                "status",
                "provider",
                "provider_message_id",
                "error",
                "attempts",
                "sent_at",
            ]
        )

    use_bought_sms(require_tenant(), sms_sent - from_allowance)
    if retry_ids:
        send_deliveries.apply_async(
            args=[retry_ids], kwargs={"tenant_slug": require_tenant().slug}, countdown=60
        )
    return counts
