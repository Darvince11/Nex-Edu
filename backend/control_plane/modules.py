"""Which modules each school has, and the rules for switching them.

- Core modules are always on.
- An optional module is *included* when its price is GH₵0 and a *paid add-on*
  otherwise; a school may use a paid add-on only once Nex Edu grants it.
- Switching on needs the modules it depends on to be on; switching off is
  refused while another switched-on module depends on it.
- Switching off never deletes records. If the school still has open records
  (unpaid invoices, waiting applications), the caller must confirm first.
- Every change is kept in ``TenantModuleChange`` and the platform audit log.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from control_plane.audit import record_platform_event
from control_plane.models import ModuleOffer, Tenant, TenantModule, TenantModuleChange
from control_plane.tenancy import tenant_context
from core.modules import BY_CODE, CORE, MODULES, Module, dependents_of


class OpenRecords(APIException):
    """Switching off would leave records the school still needs to deal with."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "module_has_open_records"

    def __init__(self, module: Module, records: list[str]) -> None:
        super().__init__(
            {
                "detail": f"{module.name} still has {', '.join(records)}. Nothing is deleted; "
                "confirm to switch it off anyway.",
                "code": self.default_code,
                "open_records": records,
            }
        )


def prices() -> dict[str, int]:
    stored = dict(ModuleOffer.objects.values_list("code", "price_pesewas"))
    return {m.code: stored.get(m.code, 0) for m in MODULES if not m.core}


def _rows(tenant: Tenant) -> dict[str, TenantModule]:
    return {row.code: row for row in TenantModule.objects.filter(tenant=tenant)}


def _entitled(code: str, row: TenantModule | None, price: int) -> bool:
    return price == 0 or bool(row and row.granted)


def _active(module: Module, row: TenantModule | None, price: int) -> bool:
    if module.core:
        return True
    if not module.available or not _entitled(module.code, row, price):
        return False
    return row.active if row else module.default_on


def active_modules(tenant: Tenant) -> frozenset[str]:
    """Codes of every module switched on for the school (core included)."""
    rows, cost = _rows(tenant), prices()
    return frozenset(m.code for m in MODULES if _active(m, rows.get(m.code), cost.get(m.code, 0)))


def is_active(tenant: Tenant, code: str) -> bool:
    return code in CORE or code in active_modules(tenant)


def catalogue(tenant: Tenant) -> list[dict[str, Any]]:
    rows, cost = _rows(tenant), prices()
    result = []
    for m in MODULES:
        row = rows.get(m.code)
        price = cost.get(m.code, 0)
        result.append(
            {
                "code": m.code,
                "name": m.name,
                "description": m.description,
                "core": m.core,
                "available": m.available,
                "depends": [{"code": d, "name": BY_CODE[d].name} for d in m.depends],
                "price_pesewas": 0 if m.core else price,
                "entitled": m.core or _entitled(m.code, row, price),
                "active": _active(m, row, price),
            }
        )
    return result


def history(tenant: Tenant, limit: int = 50) -> list[dict[str, Any]]:
    return [
        {
            "code": c.code,
            "module": BY_CODE[c.code].name if c.code in BY_CODE else "",
            "action": c.action,
            "action_label": c.get_action_display(),
            "actor_email": c.actor_email,
            "by_platform": c.by_platform,
            "reason": c.reason,
            "at": c.at,
        }
        for c in tenant.module_changes.all()[:limit]
    ]


def choices_confirmed(tenant: Tenant) -> bool:
    return TenantModuleChange.objects.filter(
        tenant=tenant, action=TenantModuleChange.Action.CONFIRMED
    ).exists()


def _module(code: str) -> Module:
    module = BY_CODE.get(code)
    if module is None:
        raise ValidationError({"code": "Unknown module."})
    if module.core:
        raise ValidationError({"code": f"{module.name} is part of every school and is always on."})
    if not module.available:
        raise ValidationError({"code": f"{module.name} isn't available yet."})
    return module


def _record(
    *, tenant: Tenant, code: str, action: str, request: Any, by_platform: bool, reason: str = ""
) -> None:
    actor = getattr(request, "user", None)
    TenantModuleChange.objects.create(
        tenant=tenant,
        code=code,
        action=action,
        actor_email=getattr(actor, "email", "") or "",
        by_platform=by_platform,
        reason=reason[:300],
    )
    record_platform_event(
        action=f"module.{action}",
        request=request,
        tenant=tenant,
        data={"module": code, "by_platform": by_platform},
        reason=reason,
    )


def set_active(
    *,
    tenant: Tenant,
    code: str,
    active: bool,
    request: Any,
    confirm: bool = False,
    by_platform: bool = False,
    reason: str = "",
) -> None:
    module = _module(code)
    with transaction.atomic():
        row, _ = TenantModule.objects.select_for_update().get_or_create(
            tenant=tenant, code=code, defaults={"active": _active(module, None, prices()[code])}
        )
        current = active_modules(tenant)
        if active:
            if not _entitled(code, row, prices()[code]):
                raise PermissionDenied(
                    f"{module.name} is a paid add-on. Ask Nex Edu to add it to your subscription."
                )
            missing = [BY_CODE[d].name for d in module.depends if d not in current]
            if missing:
                raise ValidationError({"code": f"Switch on {' and '.join(missing)} first."})
        else:
            needed_by = [m.name for m in dependents_of(code) if m.code in current]
            if needed_by:
                raise ValidationError(
                    {"code": f"Switch off {' and '.join(needed_by)} first; it needs {module.name}."}
                )
            if module.open_records and not confirm:
                with tenant_context(tenant):
                    records = module.open_records()
                if records:
                    raise OpenRecords(module, records)
        if row.active == active and (code in current) == active:
            return
        row.active = active
        row.save(update_fields=["active", "updated_at"])
        _record(
            tenant=tenant,
            code=code,
            action=TenantModuleChange.Action.ACTIVATED
            if active
            else TenantModuleChange.Action.DEACTIVATED,
            request=request,
            by_platform=by_platform,
            reason=reason,
        )


def set_granted(*, tenant: Tenant, code: str, granted: bool, request: Any, reason: str) -> None:
    """Nex Edu adds or removes a paid add-on. Removing it also switches it off."""
    _module(code)
    if not reason.strip():
        raise ValidationError({"reason": "Say why (for example the payment reference)."})
    with transaction.atomic():
        row, _ = TenantModule.objects.select_for_update().get_or_create(
            tenant=tenant, code=code, defaults={"active": granted}
        )
        if row.granted == granted:
            return
        row.granted = granted
        if granted:
            row.active = True
        else:
            row.active = False
        row.save(update_fields=["granted", "active", "updated_at"])
        _record(
            tenant=tenant,
            code=code,
            action=TenantModuleChange.Action.GRANTED
            if granted
            else TenantModuleChange.Action.REVOKED,
            request=request,
            by_platform=True,
            reason=reason,
        )


def confirm_choices(*, tenant: Tenant, request: Any) -> None:
    """The proprietor has reviewed the modules (ticks the set-up checklist step)."""
    _record(
        tenant=tenant,
        code="",
        action=TenantModuleChange.Action.CONFIRMED,
        request=request,
        by_platform=False,
    )


def set_price(*, code: str, price_pesewas: int, request: Any, reason: str) -> None:
    _module(code)
    if not reason.strip():
        raise ValidationError({"reason": "Say why the price is changing."})
    offer, _ = ModuleOffer.objects.get_or_create(code=code)
    before = offer.price_pesewas
    if before == price_pesewas:
        return
    offer.price_pesewas = price_pesewas
    offer.save(update_fields=["price_pesewas", "updated_at"])
    record_platform_event(
        action="billing.module_price_changed",
        request=request,
        target=offer,
        data={"module": code, "before_pesewas": before, "after_pesewas": price_pesewas},
        reason=reason,
    )
