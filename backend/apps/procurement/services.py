"""The buying chain:

1. Any member of staff asks (a requisition).
2. The head teacher approves; above the school's limit the proprietor approves too.
   Nobody approves their own request.
3. The bursar turns it into a purchase order to a supplier, choosing the account
   it's spent on.
4. Goods received: lines linked to a stores item go into stock, and the books
   record what's owed:      <expense account> DR  /  Owed to suppliers CR
5. Paying the supplier:     Owed to suppliers DR  /  Cash and bank CR
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.http import HttpRequest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.finance.models import LedgerAccount
from apps.finance.services import CASH, post_entry
from apps.inventory import services as stores
from apps.inventory.models import Item, Supplier
from control_plane.models import Membership
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm, permissions_for_roles

from .models import ProcurementSettings, PurchaseOrder, Requisition

PAYABLE = "2400"


def _next_number(model: Any, prefix: str) -> str:
    highest = 0
    for number in model.objects.filter(number__startswith=prefix).values_list("number", flat=True):
        tail = number[len(prefix) :]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"{prefix}{highest + 1:05d}"


def _holders(perm: str) -> set[Any]:
    from control_plane.models import Role

    rows = Membership.objects.filter(tenant=require_tenant(), is_active=True)
    if perm != Perm.PROCUREMENT_FINAL:
        rows = rows.exclude(role=Role.OWNER)
    return {m.user_id for m in rows if perm in permissions_for_roles([m.role])}


def _notify(user_ids: set[Any], title: str, body: str, data: dict[str, Any]) -> None:
    from apps.communication.services import notify_users

    if user_ids:
        notify_users(user_ids, kind="procurement", title=title, body=body, data=data)


def clean_lines(raw: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(raw, list) or not raw:
        raise ValidationError({"lines": "Add at least one thing to buy."})
    lines, total = [], 0
    for i, line in enumerate(raw, start=1):
        try:
            qty = int(line["quantity"])
            cost = int(line["unit_cost_pesewas"])
            description = str(line["description"]).strip()[:120]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(
                {"lines": f"Line {i} needs a description, quantity and price."}
            ) from exc
        if not description or not 1 <= qty <= 100_000 or not 0 <= cost <= 100_000_000:
            raise ValidationError({"lines": f"Line {i} isn't right."})
        item = line.get("item")
        if item is not None and not Item.objects.filter(pk=item).exists():
            raise ValidationError({"lines": f"Line {i}: no such stores item."})
        lines.append(
            {"description": description, "item": item, "quantity": qty, "unit_cost_pesewas": cost}
        )
        total += qty * cost
    return lines, total


def request(
    *, request: HttpRequest, purpose: str, lines: Any, needed_by: dt.date | None
) -> Requisition:
    clean, total = clean_lines(lines)
    with tenant_atomic():
        req = Requisition.objects.create(
            number=_next_number(Requisition, "REQ-"),
            purpose=purpose.strip(),
            lines=clean,
            total_pesewas=total,
            needed_by=needed_by,
            requested_by=request.user.pk,
        )
        record_event(
            action="procurement.requested",
            request=request,
            target=req,
            after={"total_pesewas": total},
        )
    _notify(
        _holders(Perm.PROCUREMENT_APPROVE) - {request.user.pk},
        f"Purchase request {req.number}",
        f"{req.purpose}: GH₵{total / 100:,.2f}",
        {"requisition": str(req.pk)},
    )
    return req


def decide(
    *, request: HttpRequest, req: Requisition, approve: bool, note: str, perms: Any
) -> Requisition:
    if req.requested_by == request.user.pk:
        raise PermissionDenied("Someone else must approve your own request.")
    limit = ProcurementSettings.load().proprietor_above_pesewas
    if req.status == Requisition.Status.SUBMITTED:
        if Perm.PROCUREMENT_APPROVE not in perms:
            raise PermissionDenied("The head teacher approves purchase requests first.")
        if approve and req.total_pesewas > limit and Perm.PROCUREMENT_FINAL not in perms:
            next_status = Requisition.Status.HEAD_APPROVED
        else:
            next_status = Requisition.Status.APPROVED if approve else Requisition.Status.REJECTED
        req.head_approved_by = request.user.pk if approve else None
    elif req.status == Requisition.Status.HEAD_APPROVED:
        if Perm.PROCUREMENT_FINAL not in perms:
            raise PermissionDenied("Requests this large also need the proprietor.")
        if req.head_approved_by == request.user.pk:
            raise PermissionDenied("A second person must give the final approval.")
        next_status = Requisition.Status.APPROVED if approve else Requisition.Status.REJECTED
        req.final_approved_by = request.user.pk if approve else None
    else:
        raise ValidationError({"detail": "This request has already been decided."})
    with tenant_atomic():
        req.status = next_status
        req.decision_note = note.strip()[:200]
        req.save()
        record_event(action=f"procurement.{next_status}", request=request, target=req)
    if next_status == Requisition.Status.HEAD_APPROVED:
        _notify(
            _holders(Perm.PROCUREMENT_FINAL),
            f"Needs your approval: {req.number}",
            f"{req.purpose}: GH₵{req.total_pesewas / 100:,.2f}",
            {"requisition": str(req.pk)},
        )
    else:
        _notify(
            {req.requested_by},
            f"Purchase request {req.get_status_display().lower()}: {req.number}",
            req.decision_note or req.purpose,
            {"requisition": str(req.pk)},
        )
        if next_status == Requisition.Status.APPROVED:
            _notify(
                _holders(Perm.PROCUREMENT_MANAGE) - {request.user.pk},
                f"Ready to order: {req.number}",
                req.purpose,
                {"requisition": str(req.pk)},
            )
    return req


def order(
    *, request: HttpRequest, req: Requisition, supplier: Supplier, account: LedgerAccount
) -> PurchaseOrder:
    if req.status != Requisition.Status.APPROVED:
        raise ValidationError({"detail": "Only approved requests can be ordered."})
    if account.type != LedgerAccount.Type.EXPENSE:
        raise ValidationError({"account": "Choose a spending account."})
    with tenant_atomic():
        po = PurchaseOrder.objects.create(
            number=_next_number(PurchaseOrder, "PO-"),
            requisition=req,
            supplier=supplier,
            account=account,
            lines=req.lines,
            total_pesewas=req.total_pesewas,
            issued_by=request.user.pk,
        )
        req.status = Requisition.Status.ORDERED
        req.save(update_fields=["status"])
        record_event(
            action="procurement.ordered",
            request=request,
            target=po,
            after={"supplier": supplier.name},
        )
    return po


def receive(
    *, request: HttpRequest, po: PurchaseOrder, invoice_reference: str, note: str
) -> PurchaseOrder:
    if po.status != PurchaseOrder.Status.ISSUED:
        raise ValidationError({"detail": "These goods have already been received."})
    LedgerAccount.objects.get_or_create(
        code=PAYABLE, defaults={"name": "Owed to suppliers", "type": LedgerAccount.Type.LIABILITY}
    )
    with tenant_atomic():
        for line in po.lines:
            if line.get("item"):
                stores.receive(
                    request=request,
                    item=Item.objects.get(pk=line["item"]),
                    quantity=line["quantity"],
                    supplier=po.supplier,
                    unit_cost_pesewas=line["unit_cost_pesewas"],
                    note=f"{po.number}",
                )
        post_entry(
            memo=f"{po.number} from {po.supplier.name}",
            source_type="purchase",
            source_id=str(po.pk),
            created_by=request.user.pk,
            lines=[(po.account.code, po.total_pesewas, 0), (PAYABLE, 0, po.total_pesewas)],
        )
        po.status = PurchaseOrder.Status.RECEIVED
        po.received_on = timezone.localdate()
        po.invoice_reference = invoice_reference.strip()[:60]
        po.received_note = note.strip()[:200]
        po.save()
        record_event(action="procurement.received", request=request, target=po)
    return po


def pay(*, request: HttpRequest, po: PurchaseOrder, reference: str) -> PurchaseOrder:
    if po.status != PurchaseOrder.Status.RECEIVED:
        raise ValidationError({"detail": "Pay the supplier once the goods are in."})
    with tenant_atomic():
        post_entry(
            memo=f"Paid {po.supplier.name} for {po.number}",
            source_type="purchase_paid",
            source_id=str(po.pk),
            created_by=request.user.pk,
            lines=[(PAYABLE, po.total_pesewas, 0), (CASH, 0, po.total_pesewas)],
        )
        po.status, po.paid_on, po.payment_reference = (
            PurchaseOrder.Status.PAID,
            timezone.localdate(),
            reference.strip()[:60],
        )
        po.save()
        record_event(action="procurement.paid", request=request, target=po)
    return po
