"""Procurement: request, approve (twice when large), order, receive into stores, pay."""

from __future__ import annotations

import pytest

from apps.finance import services as finance
from apps.finance.models import LedgerAccount
from apps.inventory.models import Item, Supplier
from apps.procurement.services import PAYABLE
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/procurement/"


@pytest.fixture
def school(campus, make_member, api):
    for code in ("inventory", "accounting", "procurement"):
        set_active(tenant=campus.tenant, code=code, active=True, request=None)
    bursar = api(make_member(campus.tenant, Role.BURSAR), campus.tenant)
    bursar.get("/api/v1/accounting/accounts/")  # seeds the spending accounts
    with tenant_context(campus.tenant):
        chalk = Item.objects.create(name="Chalk", unit="boxes")
        supplier = Supplier.objects.create(name="Accra Stationers")
        account = LedgerAccount.objects.get(code="5300")
    return {
        "teacher": api(make_member(campus.tenant, Role.TEACHER), campus.tenant),
        "head": api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant),
        "owner": api(make_member(campus.tenant, Role.OWNER), campus.tenant),
        "bursar": bursar,
        "chalk": chalk,
        "supplier": supplier,
        "account": account,
    }


def _ask(client, school, qty=10, cost=1_500):
    made = client.post(
        f"{URL}requests/",
        {
            "purpose": "Chalk for the term",
            "lines": [
                {
                    "description": "White chalk",
                    "item": school["chalk"].pk,
                    "quantity": qty,
                    "unit_cost_pesewas": cost,
                }
            ],
        },
        format="json",
    )
    assert made.status_code == 201, made.content
    return made.json()


def test_small_request_from_ask_to_paid(campus, school):
    req = _ask(school["teacher"], school)
    assert req["total_pesewas"] == 15_000 and req["number"] == "REQ-00001"
    assert (
        school["teacher"].post(f"{URL}requests/{req['id']}/decide/", {"approve": True}).status_code
        == 403
    )
    decided = school["head"].post(
        f"{URL}requests/{req['id']}/decide/", {"approve": True}, format="json"
    )
    assert decided.json()["status"] == "approved"
    po = school["bursar"].post(
        f"{URL}requests/{req['id']}/order/",
        {"supplier": school["supplier"].pk, "account": school["account"].pk},
        format="json",
    )
    assert po.status_code == 201, po.content
    po_id = po.json()["id"]
    assert (
        school["bursar"].post(f"{URL}orders/{po_id}/pay/", {}, format="json").status_code == 400
    )  # not received
    assert (
        school["bursar"]
        .post(f"{URL}orders/{po_id}/receive/", {"invoice_reference": "INV-9"}, format="json")
        .json()["status"]
        == "received"
    )
    with tenant_context(campus.tenant):
        school["chalk"].refresh_from_db()
        assert school["chalk"].in_stock == 10
        assert finance.account_balances()[PAYABLE] == -15_000
    assert (
        school["bursar"]
        .post(f"{URL}orders/{po_id}/pay/", {"reference": "CHQ 001"}, format="json")
        .json()["status"]
        == "paid"
    )
    with tenant_context(campus.tenant):
        books = finance.account_balances()
    assert books[PAYABLE] == 0 and books["5300"] == 15_000


def test_large_requests_need_the_proprietor_too(campus, school):
    req = _ask(
        school["teacher"], school, qty=100, cost=10_000
    )  # GH₵10,000, over the GH₵5,000 limit
    head = (
        school["head"]
        .post(f"{URL}requests/{req['id']}/decide/", {"approve": True}, format="json")
        .json()
    )
    assert head["status"] == "head_approved"
    assert (
        school["head"]
        .post(f"{URL}requests/{req['id']}/decide/", {"approve": True}, format="json")
        .status_code
        == 403
    )
    final = (
        school["owner"]
        .post(f"{URL}requests/{req['id']}/decide/", {"approve": True}, format="json")
        .json()
    )
    assert final["status"] == "approved"


def test_nobody_approves_their_own_and_staff_see_only_theirs(campus, school):
    own = _ask(school["head"], school)
    assert (
        school["head"]
        .post(f"{URL}requests/{own['id']}/decide/", {"approve": True}, format="json")
        .status_code
        == 403
    )
    _ask(school["teacher"], school)
    assert len(school["teacher"].get(f"{URL}requests/").json()) == 1
    assert school["teacher"].get(f"{URL}orders/").status_code == 403
    rejected = school["owner"].post(
        f"{URL}requests/{own['id']}/decide/",
        {"approve": False, "note": "Not this term"},
        format="json",
    )
    assert rejected.json()["status"] == "rejected"
    assert (
        school["head"]
        .patch(f"{URL}settings/", {"proprietor_above_pesewas": 1}, format="json")
        .status_code
        == 403
    )
