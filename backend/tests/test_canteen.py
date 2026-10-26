"""The canteen: wallets, the till, meal plans, and the books balancing."""

from __future__ import annotations

import pytest

from apps.canteen import services as canteen
from apps.communication.models import Notification
from apps.finance import services as finance
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/canteen/"


@pytest.fixture
def till(campus, make_member, make_student, api):
    set_active(tenant=campus.tenant, code="canteen", active=True, request=None)
    bursar = api(make_member(campus.tenant, Role.BURSAR), campus.tenant)
    rice = bursar.post(
        f"{URL}menu/", {"name": "Jollof rice", "price_pesewas": 800}, format="json"
    ).json()
    water = bursar.post(
        f"{URL}menu/", {"name": "Sachet water", "kind": "drink", "price_pesewas": 50}, format="json"
    ).json()
    child = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(student=child, guardian_user_id=parent_user.pk)
    return {
        "bursar": bursar,
        "seller": api(make_member(campus.tenant, Role.CANTEEN), campus.tenant),
        "parent": api(parent_user, campus.tenant),
        "parent_user": parent_user,
        "child": child,
        "rice": rice["id"],
        "water": water["id"],
    }


def _till(till, what, **body):
    return till["seller"].post(f"{URL}till/{till['child'].pk}/{what}/", body, format="json")


def test_top_up_sell_and_the_books_balance(campus, till):
    assert _till(till, "top_up", amount_pesewas=2000, reference="Cash").status_code == 201
    sold = _till(
        till, "sell", items=[{"item": till["rice"], "qty": 1}, {"item": till["water"], "qty": 2}]
    )
    assert sold.status_code == 201, sold.content
    assert sold.json()["balance_pesewas"] == 2000 - 900
    # Not more than is in the wallet.
    broke = _till(till, "sell", items=[{"item": till["rice"], "qty": 2}])
    assert broke.status_code == 400 and "Not enough" in str(broke.json())
    with tenant_context(campus.tenant):
        books = finance.account_balances()
    assert books[finance.CASH] == 2000
    assert books[canteen.WALLETS] == -1100  # still owed to the pupil
    assert books[canteen.SALES] == -900


def test_daily_limit_and_low_balance_note(campus, till):
    _till(till, "top_up", amount_pesewas=1500)
    limit = till["parent"].patch(
        f"{URL}wallets/{till['child'].pk}/", {"daily_limit_pesewas": 800}, format="json"
    )
    assert limit.status_code == 200
    assert _till(till, "sell", items=[{"item": till["rice"]}]).status_code == 201
    over = _till(till, "sell", items=[{"item": till["water"]}])
    assert over.status_code == 400 and "limit" in str(over.json())
    with tenant_context(campus.tenant):
        notes = Notification.objects.filter(
            recipient_user_id=till["parent_user"].pk, kind="canteen"
        )
        assert notes.count() == 1  # 700 left is under the GH₵10 mark
    mine = till["parent"].get(f"{URL}mine/").json()
    assert mine[0]["balance_pesewas"] == 700 and mine[0]["entries"][0]["kind"] == "purchase"


def test_meal_plan_once_a_day(campus, till):
    assert _till(till, "serve").status_code == 400  # not on a plan
    till["bursar"].post(f"{URL}plans/", {"arm": str(campus.jhs1.pk)}, format="json")
    assert _till(till, "serve").status_code == 201
    again = _till(till, "serve")
    assert again.status_code == 400 and "Already" in str(again.json())
    assert till["seller"].get(f"{URL}summary/").json()["plan_meals"] == 1


def test_refunds_need_the_bursar_and_menu_is_theirs(campus, till):
    _till(till, "top_up", amount_pesewas=1000)
    assert _till(till, "refund", amount_pesewas=500, reason="Left school").status_code == 403
    refund = till["bursar"].post(
        f"{URL}till/{till['child'].pk}/refund/",
        {"amount_pesewas": 1500, "reason": "Left"},
        format="json",
    )
    assert refund.status_code == 400  # more than the balance
    done = till["bursar"].post(
        f"{URL}till/{till['child'].pk}/refund/",
        {"amount_pesewas": 1000, "reason": "Left"},
        format="json",
    )
    assert done.status_code == 201 and done.json()["balance_pesewas"] == 0
    assert (
        till["seller"]
        .post(f"{URL}menu/", {"name": "x", "price_pesewas": 1}, format="json")
        .status_code
        == 403
    )
    # Parents can't use the till or see other wallets.
    assert till["parent"].get(f"{URL}till/{till['child'].pk}/").status_code == 403


def test_canteen_needs_fees(campus, make_member, api):
    from control_plane.modules import set_active as switch

    switch(tenant=campus.tenant, code="canteen", active=True, request=None)
    with pytest.raises(Exception, match="Canteen"):
        switch(tenant=campus.tenant, code="fees", active=False, request=None, confirm=True)
