"""Runtime registration of school database connections.

Each school database is added to Django's connection settings the first time it
is used in a process, using credentials from the secrets backend. Behind
PgBouncer this is cheap: Django keeps no persistent connections
(``CONN_MAX_AGE = 0``) and PgBouncer holds one small pool per database.
"""

from __future__ import annotations

import copy
import threading
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import connections

from control_plane.secrets import get_secrets_backend

if TYPE_CHECKING:
    from control_plane.models import Tenant

_lock = threading.Lock()


def build_db_settings(credentials: dict[str, Any]) -> dict[str, Any]:
    """Make a full Django DATABASES entry from stored credentials.

    Starts from the control-plane entry so every key Django expects is present,
    then overrides connection details. Nothing is inherited from the
    control-plane credentials themselves.
    """
    base = copy.deepcopy(connections.settings["default"])
    base.update(
        {
            "ENGINE": credentials["ENGINE"],
            "NAME": credentials["NAME"],
            "USER": credentials.get("USER", ""),
            "PASSWORD": credentials.get("PASSWORD", ""),
            "HOST": credentials.get("HOST", ""),
            "PORT": str(credentials.get("PORT", "")),
            "OPTIONS": dict(credentials.get("OPTIONS", {})),
            "CONN_MAX_AGE": 0,
            "ATOMIC_REQUESTS": False,
        }
    )
    if credentials["ENGINE"].endswith("postgresql"):
        base["DISABLE_SERVER_SIDE_CURSORS"] = True
    base["TEST"] = {
        "NAME": None,
        "MIRROR": None,
        "MIGRATE": True,
        "CHARSET": None,
        "COLLATION": None,
    }
    return base


def ensure_tenant_connection(tenant: Tenant) -> str:
    """Register the school's database alias if needed and return it."""
    alias = tenant.db_alias
    if alias in connections.settings:
        return alias
    with _lock:
        if alias not in connections.settings:
            credentials = get_secrets_backend().get(tenant.secret_ref)
            connections.settings[alias] = build_db_settings(credentials)
    return alias


def forget_tenant_connection(alias: str) -> None:
    """Close and unregister a school database alias.

    Call this after a credential rotation so the next use re-reads the secret.
    """
    with _lock:
        if alias in connections.settings:
            try:
                connections[alias].close()
            finally:
                connections.settings.pop(alias, None)
                try:
                    del connections[alias]
                except AttributeError:
                    pass


def registered_tenant_aliases() -> list[str]:
    prefix = settings.TENANT_DB_ALIAS_PREFIX
    return [alias for alias in connections.settings if alias.startswith(prefix)]
