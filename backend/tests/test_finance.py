from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
from django.db.models import Sum

from apps.academics.models import ClassLevel
from apps.finance.models import FeeItem, FeeSchedule, Invoice, JournalLine, Payment, PaymentSettings
from apps.finance.services import account_balances
from apps.students.models import StudentGuardian
from control_plane.models import PaymentReference, Role
from control_plane.tenancy import tenant_context

SECRET = "sk_test_nexedu"
GHS = 100  # pesewas per cedi


@pytest.fixture
def fees(campus, make_member, make_student, api, settings):
    """JHS 1 tuition GH₵1,200 + a school-wide PTA levy of GH₵50; two students."""
    settings.PAYSTACK_SECRET_KEY = SECRET
    settings.FLUTTERWAVE_SECRET_KEY = "flw_test"
    settings.FLUTTERWAVE_WEBHOOK_HASH = "flw-hash"
    with tenant_context(campus.tenant):
        tuition = FeeItem.objects.create(name="Tuition")
        pta = FeeItem.objects.create(name="PTA levy")
        FeeSchedule.objects.create(
            term=campus.term,
            level=ClassLevel.objects.get(name="JHS 1"),
            item=tuition,
            amount_pesewas=1200 * GHS,
        )
        FeeSchedule.objects.create(term=campus.term, item=pta, amount_pesewas=50 * GHS)
        cfg = PaymentSettings.load()
        cfg.online_payments_enabled = True
        cfg.paystack_subaccount_code = "ACCT_school"
        cfg.save()
    bursar = make_member(campus.tenant, Role.BURSAR)
    parent = make_member(campus.tenant, Role.PARENT, mfa=False, email="parent@example.test")
    kofi = make_student(campus.tenant, arm=campus.jhs1, first_name="Kofi")
    esi = make_student(campus.tenant, arm=campus.basic4, first_name="Esi")
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(
            student=kofi,
            guardian_user_id=parent.pk,
            email="parent@example.test",
            phone="+233244123456",
        )
    client = api(bursar, campus.tenant)
    generated = client.post(
        "/api/v1/finance/invoices/generate/", {"term": campus.term.pk}, format="json"
    )
    assert generated.status_code == 201, generated.data
    with tenant_context(campus.tenant):
        invoices = {inv.student_id: inv for inv in Invoice.objects.all()}
    return {
        "client": client,
        "bursar": bursar,
        "parent": parent,
        "kofi": kofi,
        "esi": esi,
        "kofi_invoice": invoices[kofi.pk],
        "esi_invoice": invoices[esi.pk],
    }


def _ledger_balanced(tenant) -> None:
    with tenant_context(tenant):
        totals = JournalLine.objects.aggregate(d=Sum("debit_pesewas"), c=Sum("credit_pesewas"))
        assert totals["d"] == totals["c"]


def test_invoices_follow_level_schedules_and_regeneration_is_safe(campus, fees):
    assert fees["kofi_invoice"].total_pesewas == 1250 * GHS
    assert fees["esi_invoice"].total_pesewas == 50 * GHS  # Basic 4 pays only the levy
    assert fees["kofi_invoice"].number.startswith("INV-")
    again = fees["client"].post(
        "/api/v1/finance/invoices/generate/", {"term": campus.term.pk}, format="json"
    )
    assert again.data == {"created": 0, "skipped": 2}
    _ledger_balanced(campus.tenant)
    with tenant_context(campus.tenant):
        assert account_balances()["1200"] == 1300 * GHS  # receivable


def test_manual_payment_part_then_full(campus, fees):
    url = f"/api/v1/finance/invoices/{fees['kofi_invoice'].pk}/record_payment/"
    part = fees["client"].post(url, {"amount_pesewas": 500 * GHS, "method": "cash"}, format="json")
    assert part.status_code == 201, part.data
    assert part.data["receipt_number"].startswith("RCT-")
    detail = fees["client"].get(f"/api/v1/finance/invoices/{fees['kofi_invoice'].pk}/").data
    assert detail["status"] == "part_paid"
    assert detail["balance_pesewas"] == 750 * GHS
    # Overpayment: the excess is recorded as fees paid in advance, not lost.
    fees["client"].post(
        url, {"amount_pesewas": 800 * GHS, "method": "bank_transfer"}, format="json"
    )
    with tenant_context(campus.tenant):
        invoice = Invoice.objects.get(pk=fees["kofi_invoice"].pk)
        assert invoice.status == "paid"
        assert account_balances()["2100"] == -50 * GHS  # liability (credit balance)
    _ledger_balanced(campus.tenant)
    receipt = fees["client"].get(f"/api/v1/finance/payments/{part.data['id']}/receipt/")
    assert receipt["Content-Type"] == "application/pdf"


def test_discount_and_void(campus, fees):
    inv = fees["esi_invoice"]
    discounted = fees["client"].post(
        f"/api/v1/finance/invoices/{inv.pk}/discount/",
        {"description": "Sibling discount", "amount_pesewas": 10 * GHS},
        format="json",
    )
    assert discounted.data["total_pesewas"] == 40 * GHS
    voided = fees["client"].post(
        f"/api/v1/finance/invoices/{inv.pk}/void/", {"reason": "Student withdrew"}, format="json"
    )
    assert voided.data["status"] == "void"
    _ledger_balanced(campus.tenant)
    with tenant_context(campus.tenant):
        assert account_balances()["1200"] == 1250 * GHS  # only Kofi's invoice remains


def test_parents_see_and_pay_only_their_childrens_invoices(campus, fees, api):
    parent = api(fees["parent"], campus.tenant)
    listed = parent.get("/api/v1/finance/invoices/").data
    assert [i["student_name"] for i in listed] == [fees["kofi"].full_name]
    other = parent.post(
        f"/api/v1/finance/invoices/{fees['esi_invoice'].pk}/pay/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="k1",
    )
    assert other.status_code == 404
    assert (
        parent.post(
            f"/api/v1/finance/invoices/{fees['kofi_invoice'].pk}/record_payment/",
            {"amount_pesewas": 100, "method": "cash"},
            format="json",
        ).status_code
        == 403
    )


def _paystack(calls: list[httpx.Request], *, verify_status="success", amount=None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        if request.url.path == "/transaction/initialize":
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "status": True,
                    "data": {
                        "authorization_url": f"https://checkout.paystack.com/{body['reference']}",
                        "reference": body["reference"],
                    },
                },
            )
        if request.url.path.startswith("/transaction/verify/"):
            ref = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json={
                    "status": True,
                    "data": {
                        "status": verify_status,
                        "reference": ref,
                        "amount": amount,
                        "currency": "GHS",
                        "id": 99,
                        "paid_at": "2026-10-19T10:00:00Z",
                        "channel": "mobile_money",
                        "customer": {"email": "parent@example.test"},
                    },
                },
            )
        return httpx.Response(404)

    return handler


def _start(campus, fees, api, key="pay-1", amount=None):
    body = {"provider": "paystack"} | ({"amount_pesewas": amount} if amount else {})
    return api(fees["parent"], campus.tenant).post(
        f"/api/v1/finance/invoices/{fees['kofi_invoice'].pk}/pay/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


def test_online_payment_checkout_is_idempotent(campus, fees, api, mock_http):
    calls: list[httpx.Request] = []
    mock_http(_paystack(calls))
    first = _start(campus, fees, api)
    assert first.status_code == 201, first.data
    assert first.data["authorization_url"].startswith("https://checkout.paystack.com/")
    init = json.loads(calls[0].content)
    assert init["currency"] == "GHS"
    assert init["amount"] == 1250 * GHS
    assert init["channels"][0] == "mobile_money"
    assert init["subaccount"] == "ACCT_school"
    again = _start(campus, fees, api)
    assert again.data["id"] == first.data["id"]
    assert len(calls) == 1
    assert PaymentReference.objects.filter(
        reference=first.data["reference"], tenant=campus.tenant
    ).exists()


def test_missing_idempotency_key_and_overpayment_are_refused(campus, fees, api, mock_http):
    mock_http(_paystack([]))
    client = api(fees["parent"], campus.tenant)
    url = f"/api/v1/finance/invoices/{fees['kofi_invoice'].pk}/pay/"
    assert client.post(url, {}, format="json").status_code == 400
    assert _start(campus, fees, api, key="k2", amount=5000 * GHS).status_code == 400


def _webhook(client, reference, secret=SECRET):
    body = json.dumps({"event": "charge.success", "data": {"reference": reference}}).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    return client.generic(
        "POST",
        "/api/v1/webhooks/paystack/",
        body,
        content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE=signature,
    )


def test_webhook_credits_once_after_verification(campus, fees, api, mock_http, client):
    calls: list[httpx.Request] = []
    mock_http(_paystack(calls, amount=1250 * GHS))
    reference = _start(campus, fees, api).data["reference"]

    assert _webhook(client, reference, secret="wrong").status_code == 401
    assert _webhook(client, reference).status_code == 200
    assert _webhook(client, reference).status_code == 200  # Paystack retries are harmless
    with tenant_context(campus.tenant):
        payment = Payment.objects.get(reference=reference)
        assert payment.status == "success"
        assert payment.amount_received_pesewas == 1250 * GHS
        assert Invoice.objects.get(pk=fees["kofi_invoice"].pk).status == "paid"
        assert Payment.objects.filter(status="success").count() == 1
        assert account_balances()["1150"] == 1250 * GHS  # online clearing
    verify_calls = [c for c in calls if "/verify/" in c.url.path]
    assert len(verify_calls) == 1  # the retry saw the payment already credited and stopped
    _ledger_balanced(campus.tenant)


def test_webhook_for_failed_charge_does_not_credit(campus, fees, api, mock_http, client):
    mock_http(_paystack([], verify_status="failed", amount=0))
    reference = _start(campus, fees, api).data["reference"]
    _webhook(client, reference)
    with tenant_context(campus.tenant):
        assert Payment.objects.get(reference=reference).status == "failed"
        assert Invoice.objects.get(pk=fees["kofi_invoice"].pk).paid_pesewas == 0


def test_webhook_for_unknown_reference_is_ignored(campus, fees, client):
    assert _webhook(client, "NXEUNKNOWN").status_code == 200
    with tenant_context(campus.tenant):
        assert not Payment.objects.filter(status="success").exists()


def test_flutterwave_webhook_requires_hash(campus, fees, client):
    body = json.dumps({"event": "charge.completed", "data": {"tx_ref": "x"}})
    assert (
        client.post(
            "/api/v1/webhooks/flutterwave/",
            body,
            content_type="application/json",
            HTTP_VERIF_HASH="nope",
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/webhooks/flutterwave/",
            body,
            content_type="application/json",
            HTTP_VERIF_HASH="flw-hash",
        ).status_code
        == 200
    )


def test_return_page_verify(campus, fees, api, mock_http):
    mock_http(_paystack([], amount=1250 * GHS))
    payment = _start(campus, fees, api).data
    verified = api(fees["parent"], campus.tenant).post(
        f"/api/v1/finance/payments/{payment['id']}/verify/"
    )
    assert verified.status_code == 200
    assert verified.data["status"] == "success"


def test_finance_summary(campus, fees):
    fees["client"].post(
        f"/api/v1/finance/invoices/{fees['esi_invoice'].pk}/record_payment/",
        {"amount_pesewas": 50 * GHS, "method": "cash"},
        format="json",
    )
    summary = fees["client"].get(f"/api/v1/finance/summary/?term={campus.term.pk}").data
    assert summary["billed_pesewas"] == 1300 * GHS
    assert summary["collected_pesewas"] == 50 * GHS
    assert summary["outstanding_pesewas"] == 1250 * GHS
    assert summary["invoices"]["paid"] == 1
