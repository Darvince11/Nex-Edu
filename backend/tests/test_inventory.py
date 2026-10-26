"""The stores: stock in and out, counts, requests from staff, low-stock notes, assets."""

from __future__ import annotations

import pytest

from apps.communication.models import Notification
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/inventory/"


@pytest.fixture
def stores(campus, make_member, api):
    set_active(tenant=campus.tenant, code="inventory", active=True, request=None)
    keeper_user = make_member(campus.tenant, Role.STORE_KEEPER)
    keeper = api(keeper_user, campus.tenant)
    chalk = keeper.post(
        f"{URL}items/", {"name": "White chalk", "unit": "boxes", "reorder_level": 5}, format="json"
    )
    assert chalk.status_code == 201, chalk.content
    teacher_user = make_member(campus.tenant, Role.TEACHER)
    return {
        "keeper": keeper,
        "keeper_user": keeper_user,
        "teacher": api(teacher_user, campus.tenant),
        "teacher_user": teacher_user,
        "chalk": chalk.json()["id"],
    }


def test_stock_in_and_out_never_below_zero(campus, stores):
    keeper, chalk = stores["keeper"], stores["chalk"]
    supplier = keeper.post(f"{URL}suppliers/", {"name": "Accra Stationers"}, format="json").json()
    got = keeper.post(
        f"{URL}items/{chalk}/receive/",
        {"quantity": 20, "supplier": supplier["id"], "unit_cost_pesewas": 1500},
        format="json",
    )
    assert got.json()["in_stock"] == 20
    out = keeper.post(
        f"{URL}items/{chalk}/issue/", {"quantity": 8, "issued_to": "JHS 1 A"}, format="json"
    )
    assert out.json()["in_stock"] == 12
    too_many = keeper.post(
        f"{URL}items/{chalk}/issue/", {"quantity": 13, "issued_to": "JHS 2"}, format="json"
    )
    assert too_many.status_code == 400 and "Only 12" in str(too_many.json())
    counted = keeper.post(f"{URL}items/{chalk}/count/", {"counted": 10}, format="json")
    assert counted.json()["in_stock"] == 10
    history = keeper.get(f"{URL}items/{chalk}/movements/").json()
    assert [m["kind"] for m in history] == ["adjusted", "issued", "received"]
    assert history[2]["supplier_name"] == "Accra Stationers"


def test_staff_ask_and_the_stores_issue(campus, stores):
    keeper, chalk = stores["keeper"], stores["chalk"]
    keeper.post(f"{URL}items/{chalk}/receive/", {"quantity": 7}, format="json")
    asked = stores["teacher"].post(
        f"{URL}requests/", {"item": chalk, "quantity": 3, "reason": "Exams"}, format="json"
    )
    assert asked.status_code == 201, asked.content
    with tenant_context(campus.tenant):
        assert Notification.objects.filter(
            recipient_user_id=stores["keeper_user"].pk, title="New stores request"
        ).exists()
    # Teachers see only their own requests and can't issue.
    assert len(stores["teacher"].get(f"{URL}requests/").json()) == 1
    assert stores["teacher"].post(f"{URL}requests/{asked.json()['id']}/approve/").status_code == 403
    done = keeper.post(f"{URL}requests/{asked.json()['id']}/approve/", {}, format="json")
    assert done.status_code == 200 and done.json()["status"] == "issued"
    item = keeper.get(f"{URL}items/{chalk}/").json()
    assert item["in_stock"] == 4 and item["low"] is True
    with tenant_context(campus.tenant):
        assert Notification.objects.filter(
            recipient_user_id=stores["teacher_user"].pk, title="Stores request is ready to collect"
        ).exists()
        assert Notification.objects.filter(
            recipient_user_id=stores["keeper_user"].pk, title="Running low: White chalk"
        ).exists()
    again = keeper.post(f"{URL}requests/{asked.json()['id']}/decline/", {}, format="json")
    assert again.status_code == 400


def test_assets_and_summary(campus, stores):
    keeper = stores["keeper"]
    made = keeper.post(
        f"{URL}assets/",
        {"tag": "GA-PRJ-001", "name": "Projector", "location": "ICT lab", "condition": "good"},
        format="json",
    )
    assert made.status_code == 201
    assert (
        keeper.post(
            f"{URL}assets/", {"tag": "GA-PRJ-001", "name": "Dup"}, format="json"
        ).status_code
        == 400
    )
    summary = keeper.get(f"{URL}summary/").json()
    assert summary["assets"] == {"good": 1} and summary["low_count"] == 1  # chalk at 0 of 5
    assert stores["teacher"].get(f"{URL}assets/").status_code == 403
    assert stores["teacher"].get(f"{URL}summary/").status_code == 403
