"""Creates a new school end to end: database, credentials, data key, schema, seed data."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Count, F, Q

from control_plane.models import TENANT_SLUG_VALIDATOR, Cell, Tenant
from control_plane.secrets import get_secrets_backend
from control_plane.tenancy import tenant_context

from .base import Provisioner, ProvisioningError, get_provisioner

logger = logging.getLogger(__name__)

RESERVED_SLUGS = frozenset(
    {"www", "api", "admin", "app", "apps", "static", "media", "mail", "status", "auth", "cdn"}
)


class NoCellCapacity(ProvisioningError):
    pass


def validate_slug(slug: str) -> str:
    slug = slug.strip().lower()
    TENANT_SLUG_VALIDATOR(slug)
    if slug in RESERVED_SLUGS:
        raise ValidationError(f"'{slug}' is reserved.")
    return slug


def choose_cell() -> Cell:
    """The accepting cell with the most free room."""
    cell = (
        Cell.objects.filter(is_accepting=True)
        .annotate(used=Count("tenants", filter=~Q(tenants__status=Tenant.Status.OFFBOARDED)))
        .filter(used__lt=F("capacity"))
        .order_by("used", "name")
        .first()
    )
    if cell is None:
        raise NoCellCapacity("No cell has free capacity. Add a cell before onboarding schools.")
    return cell


def provision_tenant(
    *,
    slug: str,
    name: str,
    is_canary: bool = False,
    provisioner: Provisioner | None = None,
    seed: bool = True,
) -> Tenant:
    from control_plane.migration_runner import migrate_tenant_database, tenant_schema_version
    from core.crypto import get_key_provider

    slug = validate_slug(slug)
    provisioner = provisioner or get_provisioner()
    cell = choose_cell() if provisioner.requires_cell else None

    tenant = Tenant.objects.create(
        slug=slug,
        name=name,
        cell=cell,
        is_canary=is_canary,
        db_name=f"school_{slug.replace('-', '_')}",
        secret_ref=f"{settings.TENANT_SECRETS_PREFIX}{slug}/db",
        status=Tenant.Status.PROVISIONING,
    )
    try:
        credentials = provisioner.create_database(tenant)
        get_secrets_backend().put(tenant.secret_ref, credentials)
        tenant.wrapped_data_key = get_key_provider().generate_wrapped_key(tenant)
        tenant.save(update_fields=["wrapped_data_key"])

        migrate_tenant_database(tenant)
        if seed:
            from apps.school.seed import seed_new_school

            with tenant_context(tenant):
                seed_new_school(name)

        tenant.status = Tenant.Status.ACTIVE
        tenant.schema_version = tenant_schema_version()
        tenant.save(update_fields=["status", "schema_version"])
    except Exception:
        logger.exception("Provisioning failed for tenant %s", slug)
        tenant.status = Tenant.Status.FAILED
        tenant.save(update_fields=["status"])
        raise
    logger.info("Provisioned tenant %s on cell %s", slug, cell.name if cell else "local")
    return tenant
