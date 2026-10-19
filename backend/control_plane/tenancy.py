"""The current school for this request or task.

Stored in a ``ContextVar`` so it is correct across threads and async tasks. Code
that touches tenant models without a tenant set fails closed with
:class:`TenantContextMissing`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from django.db.transaction import Atomic

    from control_plane.models import Tenant

_current_tenant: ContextVar[Tenant | None] = ContextVar("current_tenant", default=None)


class TenantContextMissing(RuntimeError):
    """A tenant model was used with no school selected."""


class CrossTenantAccess(RuntimeError):
    """An object loaded from one school's database was used under another school."""


def get_current_tenant() -> Tenant | None:
    return _current_tenant.get()


def require_tenant() -> Tenant:
    tenant = _current_tenant.get()
    if tenant is None:
        raise TenantContextMissing("No school is selected for this operation.")
    return tenant


@contextmanager
def tenant_context(tenant: Tenant) -> Iterator[Tenant]:
    """Run a block of code against ``tenant``'s database."""
    from control_plane.db import ensure_tenant_connection

    ensure_tenant_connection(tenant)
    token = _current_tenant.set(tenant)
    try:
        yield tenant
    finally:
        _current_tenant.reset(token)


def tenant_atomic() -> Atomic:
    """``transaction.atomic`` bound to the current school's database.

    Plain ``transaction.atomic()`` targets the control-plane database, which
    would leave school writes outside the transaction.
    """
    return transaction.atomic(using=require_tenant().db_alias)
