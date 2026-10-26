from __future__ import annotations

import logging

from celery import shared_task

from control_plane.models import Tenant
from control_plane.modules import is_active
from control_plane.tenancy import tenant_context

from . import services

logger = logging.getLogger(__name__)


@shared_task(name="compliance.remind_all")
def remind_all_tenants() -> int:
    total = 0
    for tenant in Tenant.objects.filter(status=Tenant.Status.ACTIVE).iterator():
        if not is_active(tenant, "compliance"):
            continue
        try:
            with tenant_context(tenant):
                total += services.send_reminders()
        except Exception:
            logger.exception("Compliance reminders failed for %s", tenant.slug)
    return total
