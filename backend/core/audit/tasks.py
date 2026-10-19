"""Streams new audit events to S3 (Object Lock, compliance mode) in the log-archive account."""

from __future__ import annotations

import json
import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from control_plane.models import Tenant
from control_plane.tenancy import tenant_atomic, tenant_context

from .models import AuditChainHead, AuditEvent

logger = logging.getLogger(__name__)
BATCH = 5000


def export_new_events(tenant: Tenant, s3_client: object | None = None) -> int:
    """Upload events not yet exported. Returns how many were written."""
    bucket = settings.AUDIT_EXPORT_BUCKET
    if not bucket:
        return 0
    if s3_client is None:
        import boto3

        s3_client = boto3.client("s3")

    with tenant_context(tenant):
        head, _ = AuditChainHead.objects.get_or_create(pk=1)
        events = list(
            AuditEvent.objects.filter(seq__gt=head.exported_seq).order_by("seq")[:BATCH].values()
        )
        if not events:
            return 0
        first, last = events[0]["seq"], events[-1]["seq"]
        body = "\n".join(json.dumps(e, default=str, sort_keys=True) for e in events)
        key = f"audit/{tenant.slug}/{timezone.now():%Y/%m/%d}/{first:012d}-{last:012d}.jsonl"
        s3_client.put_object(  # type: ignore[attr-defined]
            Bucket=bucket,
            Key=key,
            Body=body.encode(),
            ContentType="application/x-ndjson",
            ServerSideEncryption="aws:kms",
            ChecksumAlgorithm="SHA256",
        )
        with tenant_atomic():
            AuditChainHead.objects.filter(pk=1).update(exported_seq=last)
    return len(events)


@shared_task(name="core.audit.tasks.export_audit_events_all_tenants")
def export_audit_events_all_tenants() -> int:
    total = 0
    for tenant in Tenant.objects.filter(status=Tenant.Status.ACTIVE).iterator():
        try:
            total += export_new_events(tenant)
        except Exception:
            logger.exception("Audit export failed for %s", tenant.slug)
    return total
