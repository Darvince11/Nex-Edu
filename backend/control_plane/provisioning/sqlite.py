"""Local development and tests: each school is a SQLite file.

New schools are copied from a template file that already has every school
migration applied (built once per schema version), so set-up takes a moment
instead of running every migration again. A freshly migrated school database
holds no school-specific data, so one template serves every school.
"""

from __future__ import annotations

import io
import logging
import shutil
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.conf import settings

from .base import Provisioner

if TYPE_CHECKING:
    from control_plane.models import Tenant

logger = logging.getLogger(__name__)
_template_lock = threading.Lock()
ENGINE = "django.db.backends.sqlite3"


class SqliteProvisioner(Provisioner):
    requires_cell = False

    @property
    def directory(self) -> Path:
        directory = Path(settings.TENANT_SQLITE_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _path(self, tenant: Tenant) -> Path:
        return self.directory / f"{tenant.db_name}.sqlite3"

    def template(self) -> Path | None:
        """The migrated template for the current schema, built on first use.
        None if it can't be built; set-up then migrates from scratch as before."""
        from control_plane.migration_runner import tenant_schema_version

        version = tenant_schema_version()
        target = self.directory / f"_template_{version}.sqlite3"
        if target.exists():
            return target
        with _template_lock:
            if target.exists():
                return target
            try:
                self._build_template(target, version)
            except Exception:
                logger.exception("Couldn't build the school database template")
                return None
        return target

    def _build_template(self, target: Path, version: str) -> None:
        from django.core.management import call_command
        from django.db import connections

        from control_plane.db import build_db_settings, forget_tenant_connection

        building = target.with_suffix(".building")
        building.unlink(missing_ok=True)
        alias = f"{settings.TENANT_DB_ALIAS_PREFIX}template_{version}"
        # Drop any connection cached under this name (an earlier build in this
        # process), or migrate would write to that build's file.
        forget_tenant_connection(alias)
        connections.settings[alias] = build_db_settings({"ENGINE": ENGINE, "NAME": str(building)})
        try:
            call_command(
                "migrate", database=alias, interactive=False, verbosity=0, stdout=io.StringIO()
            )
        finally:
            forget_tenant_connection(alias)
        building.replace(target)
        for old in self.directory.glob("_template_*.sqlite3"):
            if old != target:
                old.unlink(missing_ok=True)
        logger.info("Built the school database template for schema %s", version)

    def create_database(self, tenant: Tenant) -> dict[str, Any]:
        path = self._path(tenant)
        template = self.template()
        if template is not None and not path.exists():
            shutil.copyfile(template, path)
        return {"ENGINE": ENGINE, "NAME": str(path)}

    def drop_database(self, tenant: Tenant) -> None:
        self._path(tenant).unlink(missing_ok=True)
