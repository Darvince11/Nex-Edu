"""A school's life on Nex Edu after it is set up: suspended, reactivated, closed, destroyed.

- **Suspended**: nobody can use the school (the middleware refuses it). Either by
  Nex Edu staff, or automatically when an invoice is 30 days past due (owner's
  decision, 26 Oct 2026); paying reactivates a school suspended for that.
- **Closed (offboarded)**: the proprietor gets a full export straight away; the
  database stays locked for 90 days in case they come back, then
- **Destroyed (purged)**: the school's data key is deleted (so encrypted fields,
  backups included, can never be read again), its database is dropped and its
  files removed. The control-plane record stays, marked purged, for the audit trail.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import logging
import zipfile
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from control_plane.audit import record_platform_event
from control_plane.models import Membership, Role, Tenant
from control_plane.tenancy import tenant_context

logger = logging.getLogger(__name__)

RETENTION_DAYS = 90


class Reason:
    NONPAYMENT = "nonpayment"
    PLATFORM = "platform"
    CLOSED = "closed"


def owner_emails(tenant: Tenant) -> list[str]:
    return list(
        Membership.objects.filter(tenant=tenant, role=Role.OWNER, is_active=True)
        .values_list("user__email", flat=True)
        .distinct()
    )


def _tell_owners(tenant: Tenant, subject: str, body: str) -> None:
    emails = owner_emails(tenant)
    if emails:
        send_mail(subject, body, None, emails, fail_silently=True)


def _set_status(tenant: Tenant, status: str, reason: str, note: str) -> None:
    tenant.status, tenant.status_reason, tenant.status_note = status, reason, note
    tenant.status_changed_at = timezone.now()
    tenant.save(update_fields=["status", "status_reason", "status_note", "status_changed_at"])


@transaction.atomic
def suspend(
    tenant: Tenant, *, reason: str, note: str, request: Any = None, automatic: bool = False
) -> Tenant:
    tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
    if tenant.status != Tenant.Status.ACTIVE:
        raise ValidationError({"detail": "Only an active school can be suspended."})
    if not automatic and not note.strip():
        raise ValidationError({"reason": "Say why the school is being suspended."})
    _set_status(tenant, Tenant.Status.SUSPENDED, reason, note.strip())
    record_platform_event(
        action="tenant.suspended",
        request=request,
        tenant=tenant,
        target=tenant,
        data={"reason": reason, "automatic": automatic},
        reason=note.strip(),
    )
    if reason == Reason.NONPAYMENT:
        body = (
            f"{tenant.name} has been suspended on Nex Edu because an invoice is more than "
            "30 days overdue. Staff, parents and pupils can't sign in until it is paid.\n\n"
            f"Pay now: {settings.FRONTEND_URL}/account/billing?school={tenant.slug}\n"
            "The school is reactivated as soon as the payment comes through."
        )
    else:
        body = (
            f"{tenant.name} has been suspended on Nex Edu.\n\nReason: {note.strip()}\n\n"
            "Reply to this email or contact support@nexedu.com.gh to resolve it."
        )
    transaction.on_commit(lambda: _tell_owners(tenant, f"{tenant.name} is suspended", body))
    return tenant


@transaction.atomic
def reactivate(
    tenant: Tenant, *, note: str, request: Any = None, automatic: bool = False
) -> Tenant:
    tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
    if tenant.status == Tenant.Status.OFFBOARDED and not tenant.purged_at:
        pass  # a closed school coming back inside the 90 days
    elif tenant.status != Tenant.Status.SUSPENDED:
        raise ValidationError({"detail": "Only a suspended or closed school can be reactivated."})
    was = tenant.status
    _set_status(tenant, Tenant.Status.ACTIVE, "", "")
    if was == Tenant.Status.OFFBOARDED:
        tenant.purge_after = None
        tenant.save(update_fields=["purge_after"])
    record_platform_event(
        action="tenant.reactivated",
        request=request,
        tenant=tenant,
        target=tenant,
        data={"was": was, "automatic": automatic},
        reason=note.strip(),
    )
    transaction.on_commit(
        lambda: _tell_owners(
            tenant,
            f"{tenant.name} is active again",
            f"{tenant.name} is active on Nex Edu again. Everyone can sign in as before.",
        )
    )
    return tenant


def build_export(tenant: Tenant) -> str:
    """Every record and file of the school in one zip, under the school's own prefix.
    Returns the storage key. Only the proprietor can download it."""
    buffer = io.BytesIO()
    prefix = f"tenants/{tenant.slug}/"
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        counts: dict[str, int] = {}
        with tenant_context(tenant):
            for label in settings.TENANT_APP_LABELS:
                for model in apps.get_app_config(label).get_models():
                    rows = model.objects.using(tenant.db_alias).all()
                    counts[model._meta.label] = rows.count()
                    if counts[model._meta.label]:
                        archive.writestr(
                            f"data/{model._meta.label}.json",
                            serializers.serialize("json", rows, indent=1),
                        )
        files = 0
        for key in _all_keys(prefix):
            if "/exports/" in key:
                continue
            with default_storage.open(key, "rb") as handle:
                archive.writestr(f"files/{key[len(prefix) :]}", handle.read())
            files += 1
        archive.writestr(
            "README.txt",
            f"Everything {tenant.name} kept on Nex Edu, exported "
            f"{timezone.now():%d %B %Y %H:%M} UTC.\n\n"
            "data/  one JSON file per kind of record (Django's JSON format)\n"
            "files/ uploaded files, report cards and receipts\n",
        )
        archive.writestr(
            "manifest.json", json.dumps({"school": tenant.slug, "records": counts, "files": files})
        )
    key = f"{prefix}exports/{tenant.slug}-{timezone.now():%Y%m%d%H%M%S}.zip"
    return default_storage.save(key, ContentFile(buffer.getvalue()))


def _all_keys(prefix: str) -> list[str]:
    """Every stored file under a prefix (filesystem and S3 both list directories)."""
    keys: list[str] = []
    try:
        folders, files = default_storage.listdir(prefix)
    except (FileNotFoundError, NotADirectoryError):
        return keys
    keys += [f"{prefix}{name}" for name in files]
    for folder in folders:
        keys += _all_keys(f"{prefix}{folder}/")
    return keys


def offboard(tenant: Tenant, *, note: str, request: Any = None) -> Tenant:
    """Close the school: export, lock, and schedule destruction in 90 days."""
    if tenant.status not in (Tenant.Status.ACTIVE, Tenant.Status.SUSPENDED):
        raise ValidationError({"detail": "This school is already closed."})
    if not note.strip():
        raise ValidationError({"reason": "Say why the school is leaving."})
    key = build_export(tenant)
    with transaction.atomic():
        tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
        _set_status(tenant, Tenant.Status.OFFBOARDED, Reason.CLOSED, note.strip())
        tenant.export_key = key
        tenant.purge_after = timezone.localdate() + dt.timedelta(days=RETENTION_DAYS)
        tenant.save(update_fields=["export_key", "purge_after"])
        record_platform_event(
            action="tenant.offboarded",
            request=request,
            tenant=tenant,
            target=tenant,
            data={"purge_after": tenant.purge_after.isoformat()},
            reason=note.strip(),
        )
    _tell_owners(
        tenant,
        f"{tenant.name} has left Nex Edu: your data",
        f"{tenant.name} is closed on Nex Edu. Download everything the school kept here:\n"
        f"{settings.FRONTEND_URL}/account/billing?school={tenant.slug}\n\n"
        f"The data stays locked until {tenant.purge_after:%d %B %Y}. If you come back before "
        "then, everything is restored as it was. After that it is destroyed for good and "
        "can't be recovered.",
    )
    return tenant


def purge(tenant: Tenant) -> bool:
    """Destroy a closed school's data for good. Returns True when done."""
    from control_plane.db import forget_tenant_connection
    from control_plane.provisioning.base import get_provisioner

    if tenant.status != Tenant.Status.OFFBOARDED or tenant.purged_at:
        raise ValueError(f"Refusing to purge {tenant.slug}: it is {tenant.status}.")
    forget_tenant_connection(tenant.db_alias)
    try:
        get_provisioner().drop_database(tenant)
    except Exception:
        logger.exception("Could not drop the database of %s; will retry", tenant.slug)
        return False
    for key in _all_keys(f"tenants/{tenant.slug}/"):
        default_storage.delete(key)
    with transaction.atomic():
        Tenant.objects.filter(pk=tenant.pk).update(
            wrapped_data_key=None, export_key="", purged_at=timezone.now()
        )
        record_platform_event(
            action="tenant.purged",
            tenant=tenant,
            target=tenant,
            data={"crypto_shredded": True},
        )
    return True


def purge_due() -> int:
    """Daily: destroy closed schools whose 90 days are up."""
    done = 0
    for tenant in Tenant.objects.filter(
        status=Tenant.Status.OFFBOARDED,
        purged_at__isnull=True,
        purge_after__lte=timezone.localdate(),
    ):
        done += purge(tenant)
    return done
