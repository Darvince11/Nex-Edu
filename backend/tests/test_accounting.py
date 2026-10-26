"""Accounting: spending and income in the books, voids, budgets and reports."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.finance import services as finance
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/accounting/"


@pytest.fixture
def books(campus, make_member, api):
    set_active(tenant=campus.tenant, code="accounting", active=True, request=None)
    bursar = api(make_member(campus.tenant, Role.BURSAR), campus.tenant)
    accounts = {a["name"]: a["id"] for a in bursar.get(f"{URL}accounts/").json()}
    return {
        "bursar": bursar,
        "head": api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant),
        "teacher": api(make_member(campus.tenant, Role.TEACHER), campus.tenant),
        "accounts": accounts,
    }


def _record(client, kind, account, amount, day=None, **extra):
    return client.post(
        f"{URL}transactions/",
        {
            "kind": kind,
            "date": (day or timezone.localdate()).isoformat(),
            "account": account,
            "amount_pesewas": amount,
            "party": "ECG" if kind == "expense" else "PTA",
            **extra,
        },
        format="json",
    )


def test_spending_and_income_balance_the_books(campus, books):
    utilities = books["accounts"]["Utilities (electricity, water, internet)"]
    donations = books["accounts"]["Donations and grants"]
    assert _record(books["bursar"], "expense", utilities, 45_000).status_code == 201
    assert _record(books["bursar"], "income", donations, 100_000).status_code == 201
    # The account has to match the kind.
    assert _record(books["bursar"], "expense", donations, 100).status_code == 400
    assert (
        _record(
            books["bursar"],
            "expense",
            utilities,
            100,
            day=timezone.localdate() + dt.timedelta(days=2),
        ).status_code
        == 400
    )
    with tenant_context(campus.tenant):
        balances = finance.account_balances()
    assert balances[finance.CASH] == 55_000

    tb = books["head"].get(f"{URL}reports/trial-balance/").json()
    assert tb["debit_total_pesewas"] == tb["credit_total_pesewas"]
    ie = books["head"].get(f"{URL}reports/income-expenditure/").json()
    assert ie["income_total_pesewas"] == 100_000 and ie["expenditure_total_pesewas"] == 45_000
    assert ie["surplus_pesewas"] == 55_000
    cash = books["head"].get(f"{URL}reports/cash-book/").json()
    assert cash["closing_pesewas"] == 55_000 and len(cash["rows"]) == 2
    csv = books["head"].get(f"{URL}reports/income-expenditure/", {"export": "csv"})
    assert csv["Content-Type"].startswith("text/csv") and b"Surplus (deficit)" in csv.content


def test_voiding_reverses_and_keeps_the_record(campus, books):
    utilities = books["accounts"]["Utilities (electricity, water, internet)"]
    txn = _record(books["bursar"], "expense", utilities, 20_000).json()
    assert (
        books["bursar"].post(f"{URL}transactions/{txn['id']}/void/", {}, format="json").status_code
        == 400
    )
    voided = books["bursar"].post(
        f"{URL}transactions/{txn['id']}/void/", {"reason": "Entered twice"}, format="json"
    )
    assert voided.json()["voided"] is True
    again = books["bursar"].post(
        f"{URL}transactions/{txn['id']}/void/", {"reason": "x"}, format="json"
    )
    assert again.status_code == 400
    with tenant_context(campus.tenant):
        assert finance.account_balances().get(finance.CASH, 0) == 0
    assert len(books["bursar"].get(f"{URL}transactions/").json()) == 1


def test_backdated_spending_lands_in_its_own_period(campus, books):
    repairs = books["accounts"]["Repairs and maintenance"]
    last_month = timezone.localdate() - dt.timedelta(days=40)
    _record(books["bursar"], "expense", repairs, 30_000, day=last_month)
    recent = (
        books["head"]
        .get(
            f"{URL}reports/income-expenditure/",
            {"start": (timezone.localdate() - dt.timedelta(days=7)).isoformat()},
        )
        .json()
    )
    assert recent["expenditure_total_pesewas"] == 0
    wide = (
        books["head"]
        .get(
            f"{URL}reports/income-expenditure/",
            {"start": (last_month - dt.timedelta(days=1)).isoformat()},
        )
        .json()
    )
    assert wide["expenditure_total_pesewas"] == 30_000


def test_budgets_and_who_may_do_what(campus, books):
    repairs = books["accounts"]["Repairs and maintenance"]
    set_budget = books["bursar"].put(
        f"{URL}budgets/",
        {"session": campus.session.pk, "account": repairs, "amount_pesewas": 100_000},
        format="json",
    )
    assert set_budget.status_code == 200, set_budget.content
    _record(books["bursar"], "expense", repairs, 25_000)
    report = books["head"].get(f"{URL}budgets/").json()
    row = next(r for r in report["rows"] if r["account"] == repairs)
    assert (
        row["actual_pesewas"] == 25_000
        and row["left_pesewas"] == 75_000
        and row["used_percent"] == 25.0
    )
    # The head teacher reads; only the bursar (and proprietor) records.
    assert _record(books["head"], "expense", repairs, 1).status_code == 403
    assert books["teacher"].get(f"{URL}reports/trial-balance/").status_code == 403
    made = books["bursar"].post(
        f"{URL}accounts/", {"name": "Exam fees paid to WAEC", "type": "expense"}, format="json"
    )
    assert made.status_code == 201 and made.json()["code"].startswith("5")
