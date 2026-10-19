"""Local development and tests: each school is a SQLite file."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.conf import settings

from .base import Provisioner

if TYPE_CHECKING:
    from control_plane.models import Tenant


class SqliteProvisioner(Provisioner):
    requires_cell = False

    def _path(self, tenant: Tenant) -> Path:
        directory = Path(settings.TENANT_SQLITE_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{tenant.db_name}.sqlite3"

    def create_database(self, tenant: Tenant) -> dict[str, Any]:
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": str(self._path(tenant))}

    def drop_database(self, tenant: Tenant) -> None:
        self._path(tenant).unlink(missing_ok=True)
