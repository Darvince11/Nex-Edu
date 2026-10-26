"""Stock rules: stock never goes below zero; every change is a recorded movement;
the stores are told when an item falls to its reorder level."""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.http import HttpRequest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from control_plane.models import Membership
from control_plane.tenancy import require_tenant, tenant_atomic
from core.rbac import Perm, permissions_for_roles

from .models import Item, Movement, Request, Supplier


def store_keepers() -> set[Any]:
    """Everyone who runs the stores (holds ``inventory.manage`` by role), except the proprietor."""
    from control_plane.models import Role

    rows = Membership.objects.filter(tenant=require_tenant(), is_active=True).exclude(
        role=Role.OWNER
    )
    return {m.user_id for m in rows if Perm.INVENTORY_MANAGE in permissions_for_roles([m.role])}


def _move(
    *,
    request: HttpRequest,
    item: Item,
    kind: str,
    quantity: int,
    date: dt.date | None = None,
    **extra: Any,
) -> Movement:
    with tenant_atomic():
        locked = Item.objects.select_for_update().get(pk=item.pk)
        was_low = locked.low
        after = locked.in_stock + quantity
        if after < 0:
            raise ValidationError({"quantity": f"Only {locked.in_stock} {locked.unit} in stock."})
        locked.in_stock = after
        locked.save(update_fields=["in_stock"])
        movement = Movement.objects.create(
            item=locked,
            kind=kind,
            quantity=quantity,
            stock_after=after,
            date=date or timezone.localdate(),
            recorded_by=request.user.pk,
            **extra,
        )
    if not was_low and locked.low and locked.reorder_level:
        from apps.communication.services import notify_users

        notify_users(
            store_keepers(),
            kind="inventory",
            title=f"Running low: {locked.name}",
            body=f"{locked.in_stock} {locked.unit} of {locked.name} left. Time to order more.",
            data={"item": locked.pk},
        )
    return movement


def receive(
    *,
    request: HttpRequest,
    item: Item,
    quantity: int,
    supplier: Supplier | None = None,
    unit_cost_pesewas: int | None = None,
    date: dt.date | None = None,
    note: str = "",
) -> Movement:
    if quantity <= 0:
        raise ValidationError({"quantity": "Enter how many came in."})
    return _move(
        request=request,
        item=item,
        kind=Movement.Kind.RECEIVED,
        quantity=quantity,
        date=date,
        supplier=supplier,
        unit_cost_pesewas=unit_cost_pesewas,
        note=note,
    )


def issue(
    *,
    request: HttpRequest,
    item: Item,
    quantity: int,
    issued_to: str,
    date: dt.date | None = None,
    note: str = "",
) -> Movement:
    if quantity <= 0:
        raise ValidationError({"quantity": "Enter how many went out."})
    if not issued_to.strip():
        raise ValidationError({"issued_to": "Say who it went to."})
    return _move(
        request=request,
        item=item,
        kind=Movement.Kind.ISSUED,
        quantity=-quantity,
        date=date,
        issued_to=issued_to.strip(),
        note=note,
    )


def count(*, request: HttpRequest, item: Item, counted: int, note: str = "") -> Movement | None:
    """A stock count: record the difference between what's on the shelf and the books."""
    if counted < 0:
        raise ValidationError({"counted": "Count can't be negative."})
    difference = counted - item.in_stock
    if difference == 0:
        return None
    return _move(
        request=request,
        item=item,
        kind=Movement.Kind.ADJUSTED,
        quantity=difference,
        note=note or "Stock count",
    )


def decide(*, request: HttpRequest, req: Request, approve: bool, note: str = "") -> Request:
    from apps.communication.services import notify_users

    if req.status != Request.Status.PENDING:
        raise ValidationError({"detail": "This request has already been dealt with."})
    if req.requested_by == request.user.pk:
        raise ValidationError({"detail": "Someone else must deal with your own request."})
    with tenant_atomic():
        if approve:
            name = next(iter(_names([req.requested_by]).values()), "staff")
            issue(
                request=request,
                item=req.item,
                quantity=req.quantity,
                issued_to=name,
                note=f"Request: {req.reason}"[:200],
            )
        req.status = Request.Status.ISSUED if approve else Request.Status.DECLINED
        req.decided_by = request.user.pk
        req.decided_at = timezone.now()
        req.decision_note = note[:200]
        req.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
    verdict = "is ready to collect" if approve else "was declined"
    notify_users(
        [req.requested_by],
        kind="inventory",
        title=f"Stores request {verdict}",
        body=f"{req.quantity} {req.item.unit} of {req.item.name} {verdict}."
        + (f" {note}" if note else ""),
        data={"request": str(req.pk)},
    )
    return req


def _names(ids: list[Any]) -> dict[Any, str]:
    from control_plane.models import User

    return {u.pk: u.get_full_name() or u.email for u in User.objects.filter(pk__in=ids)}
