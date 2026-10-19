"""Sends tenant models to the current school's database and everything else to
the control plane. Fails closed when no school is selected."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models

from control_plane.tenancy import CrossTenantAccess, require_tenant


def _is_tenant_model(model: type[models.Model]) -> bool:
    return model._meta.app_label in settings.TENANT_APP_LABELS


def _is_tenant_alias(alias: str | None) -> bool:
    return bool(alias) and str(alias).startswith(settings.TENANT_DB_ALIAS_PREFIX)


class TenantRouter:
    def db_for_read(self, model: type[models.Model], **hints: Any) -> str:
        if _is_tenant_model(model):
            return self._tenant_alias(hints)
        return "default"

    def db_for_write(self, model: type[models.Model], **hints: Any) -> str:
        if _is_tenant_model(model):
            return self._tenant_alias(hints)
        return "default"

    def allow_relation(self, obj1: models.Model, obj2: models.Model, **hints: Any) -> bool | None:
        db1, db2 = obj1._state.db, obj2._state.db
        if db1 and db2:
            return db1 == db2
        return None

    def allow_migrate(
        self, db: str, app_label: str, model_name: str | None = None, **hints: Any
    ) -> bool:
        if app_label in settings.TENANT_APP_LABELS:
            return _is_tenant_alias(db)
        return not _is_tenant_alias(db)

    @staticmethod
    def _tenant_alias(hints: dict[str, Any]) -> str:
        alias = require_tenant().db_alias
        instance = hints.get("instance")
        loaded_from = getattr(getattr(instance, "_state", None), "db", None)
        if _is_tenant_alias(loaded_from) and loaded_from != alias:
            raise CrossTenantAccess(
                f"Object loaded from {loaded_from} cannot be used while {alias} is selected."
            )
        return alias
