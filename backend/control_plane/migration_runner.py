"""Applies schema migrations to school databases.

Rollout order is canary schools first, then one cell at a time. The run halts at
the first wave that has a failure, so a bad migration reaches as few schools as
possible. Migrations must follow expand/contract so old and new application
code both work while schools are on different versions.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone

from control_plane.db import ensure_tenant_connection
from control_plane.models import Tenant, TenantMigrationRun


def tenant_schema_version() -> str:
    """A short fingerprint of the latest migration of every tenant app."""
    loader = MigrationLoader(None, ignore_no_migrations=True)
    leaves = sorted(
        f"{app}.{name}"
        for app, name in loader.graph.leaf_nodes()
        if app in settings.TENANT_APP_LABELS
    )
    return hashlib.sha256(",".join(leaves).encode()).hexdigest()[:16]


def migrate_tenant_database(tenant: Tenant) -> None:
    """Migrate one school database in the calling thread."""
    alias = ensure_tenant_connection(tenant)
    try:
        call_command(
            "migrate", database=alias, interactive=False, verbosity=0, stdout=io.StringIO()
        )
    finally:
        connections[alias].close()


@dataclass
class MigrationResult:
    tenant: Tenant
    started_at: datetime
    finished_at: datetime
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return not self.error


def _migrate_one(tenant: Tenant, migrate: Callable[[Tenant], None]) -> MigrationResult:
    started = timezone.now()
    try:
        migrate(tenant)
    except Exception as exc:
        return MigrationResult(tenant, started, timezone.now(), f"{type(exc).__name__}: {exc}")
    return MigrationResult(tenant, started, timezone.now())


def plan_waves(tenants: Iterable[Tenant]) -> list[list[Tenant]]:
    """Canary schools first, then one wave per cell."""
    tenants = list(tenants)
    canaries = [t for t in tenants if t.is_canary]
    by_cell: dict[str, list[Tenant]] = {}
    for tenant in tenants:
        if not tenant.is_canary:
            by_cell.setdefault(tenant.cell.name if tenant.cell else "", []).append(tenant)
    waves = [canaries] if canaries else []
    waves.extend(by_cell[name] for name in sorted(by_cell))
    return waves


def run_tenant_migrations(
    tenants: Iterable[Tenant],
    *,
    parallelism: int | None = None,
    migrate: Callable[[Tenant], None] | None = None,
    on_wave: Callable[[int, list[MigrationResult]], None] | None = None,
) -> list[MigrationResult]:
    """Migrate schools wave by wave. Returns every result up to the failing wave.

    Worker threads only touch school databases. All control-plane writes happen
    on the calling thread.
    """
    parallelism = parallelism or settings.TENANT_MIGRATION_PARALLELISM
    migrate = migrate or migrate_tenant_database
    version = tenant_schema_version()
    results: list[MigrationResult] = []

    for index, wave in enumerate(plan_waves(tenants)):
        with ThreadPoolExecutor(
            max_workers=parallelism, thread_name_prefix="tenant-migrate"
        ) as pool:
            wave_results = list(pool.map(lambda t: _migrate_one(t, migrate), wave))  # type: ignore[arg-type]

        for result in wave_results:
            TenantMigrationRun.objects.create(
                tenant=result.tenant,
                started_at=result.started_at,
                finished_at=result.finished_at,
                succeeded=result.succeeded,
                schema_version=version if result.succeeded else "",
                error=result.error,
            )
            if result.succeeded:
                Tenant.objects.filter(pk=result.tenant.pk).update(
                    schema_version=version, migrated_at=result.finished_at
                )
        results.extend(wave_results)
        if on_wave:
            on_wave(index, wave_results)
        if any(not r.succeeded for r in wave_results):
            break
    return results
