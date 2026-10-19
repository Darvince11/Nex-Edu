from __future__ import annotations

import logging

from celery import shared_task

from control_plane.models import Tenant
from control_plane.tenancy import tenant_context

from .services import process_webhook, reconcile_pending_payments

logger = logging.getLogger(__name__)


@shared_task(
    name="integrations.payments.process_webhook", bind=True, max_retries=5, default_retry_delay=30
)
def process_payment_webhook(
    self, provider_name: str, raw_body: str, headers: dict[str, str]
) -> str:  # type: ignore[no-untyped-def]
    from django.core.exceptions import PermissionDenied

    from integrations.payments import PaymentProviderError

    try:
        return process_webhook(provider_name, raw_body.encode(), headers)
    except PermissionDenied:
        logger.warning("Rejected %s webhook with a bad signature", provider_name)
        return "rejected: signature"
    except PaymentProviderError as exc:
        raise self.retry(exc=exc) from exc


@shared_task(name="integrations.payments.reconcile_all")
def reconcile_all_tenants() -> int:
    total = 0
    for tenant in Tenant.objects.filter(status=Tenant.Status.ACTIVE).iterator():
        try:
            with tenant_context(tenant):
                total += sum(reconcile_pending_payments().values())
        except Exception:
            logger.exception("Payment reconciliation failed for %s", tenant.slug)
    return total
