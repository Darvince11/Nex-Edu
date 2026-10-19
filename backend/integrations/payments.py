"""Paystack and Flutterwave clients.

Security rules, enforced by the callers in ``apps.finance.services``:
- A webhook is accepted only with a valid signature (Paystack HMAC-SHA512 of the
  raw body; Flutterwave ``verif-hash`` header), compared in constant time.
- Even a correctly signed webhook never credits money by itself: the
  transaction is re-fetched from the provider's verify API, and its amount and
  currency are checked against what was requested.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from django.conf import settings
from django.utils.dateparse import parse_datetime

from . import http


class PaymentProviderError(RuntimeError):
    pass


@dataclass
class Checkout:
    authorization_url: str
    provider_reference: str


@dataclass
class VerifiedPayment:
    reference: str
    succeeded: bool
    status: str
    amount_pesewas: int
    currency: str
    provider_transaction_id: str
    paid_at: datetime | None
    raw: dict[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    name: str

    def initialize(
        self,
        *,
        reference: str,
        amount_pesewas: int,
        email: str,
        callback_url: str,
        subaccount: str,
        metadata: dict[str, Any],
    ) -> Checkout: ...

    def verify(self, reference: str) -> VerifiedPayment: ...

    def webhook_is_authentic(self, raw_body: bytes, headers: Any) -> bool: ...

    def reference_from_webhook(self, payload: dict[str, Any]) -> str | None: ...


def _header(headers: Any, name: str) -> str:
    """Case-insensitive header lookup for both Django headers and plain dicts."""
    for key, value in dict(headers).items():
        if key.lower() == name.lower():
            return str(value)
    return ""


def _safe(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep what support staff need; drop card and customer details."""
    keep = (
        "id",
        "status",
        "reference",
        "tx_ref",
        "amount",
        "currency",
        "channel",
        "paid_at",
        "created_at",
        "gateway_response",
        "processor_response",
    )
    return {k: raw.get(k) for k in keep if k in raw}


class Paystack:
    name = "paystack"
    base_url = "https://api.paystack.co"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}

    def initialize(
        self,
        *,
        reference: str,
        amount_pesewas: int,
        email: str,
        callback_url: str,
        subaccount: str,
        metadata: dict[str, Any],
    ) -> Checkout:
        payload: dict[str, Any] = {
            "email": email,
            "amount": amount_pesewas,
            "currency": "GHS",
            # Mobile money first: most Ghanaian parents pay with MTN MoMo,
            # Telecel Cash or AirtelTigo Money.
            "channels": ["mobile_money", "card"],
            "reference": reference,
            "callback_url": callback_url,
            "metadata": metadata,
        }
        if subaccount:
            payload["subaccount"] = subaccount
            payload["bearer"] = "subaccount"
        with http.client() as c:
            r = c.post(
                f"{self.base_url}/transaction/initialize", json=payload, headers=self._headers()
            )
        body = r.json() if r.content else {}
        if r.status_code >= 400 or not body.get("status"):
            raise PaymentProviderError(f"Paystack: {body.get('message', r.status_code)}")
        return Checkout(body["data"]["authorization_url"], body["data"]["reference"])

    def verify(self, reference: str) -> VerifiedPayment:
        with http.client() as c:
            r = c.get(f"{self.base_url}/transaction/verify/{reference}", headers=self._headers())
        body = r.json() if r.content else {}
        if r.status_code >= 500 or "data" not in body:
            raise PaymentProviderError(f"Paystack verify: {body.get('message', r.status_code)}")
        data = body["data"] or {}
        status = str(data.get("status", "unknown"))
        return VerifiedPayment(
            reference=str(data.get("reference", reference)),
            succeeded=status == "success",
            status=status,
            amount_pesewas=int(data.get("amount") or 0),
            currency=str(data.get("currency", "")),
            provider_transaction_id=str(data.get("id", "")),
            paid_at=parse_datetime(data["paid_at"]) if data.get("paid_at") else None,
            raw=_safe(data),
        )

    def webhook_is_authentic(self, raw_body: bytes, headers: Any) -> bool:
        signature = _header(headers, "X-Paystack-Signature")
        expected = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(), raw_body, hashlib.sha512
        ).hexdigest()
        return bool(signature) and hmac.compare_digest(signature, expected)

    def reference_from_webhook(self, payload: dict[str, Any]) -> str | None:
        if payload.get("event") != "charge.success":
            return None
        return (payload.get("data") or {}).get("reference")


class Flutterwave:
    name = "flutterwave"
    base_url = "https://api.flutterwave.com/v3"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"}

    def initialize(
        self,
        *,
        reference: str,
        amount_pesewas: int,
        email: str,
        callback_url: str,
        subaccount: str,
        metadata: dict[str, Any],
    ) -> Checkout:
        payload: dict[str, Any] = {
            "tx_ref": reference,
            "amount": str(Decimal(amount_pesewas) / 100),
            "currency": "GHS",
            "redirect_url": callback_url,
            "customer": {"email": email},
            "meta": metadata,
            "payment_options": "mobilemoneyghana,card",
            "customizations": {"title": "School fees"},
        }
        if subaccount:
            payload["subaccounts"] = [{"id": subaccount}]
        with http.client() as c:
            r = c.post(f"{self.base_url}/payments", json=payload, headers=self._headers())
        body = r.json() if r.content else {}
        if r.status_code >= 400 or body.get("status") != "success":
            raise PaymentProviderError(f"Flutterwave: {body.get('message', r.status_code)}")
        return Checkout(body["data"]["link"], reference)

    def verify(self, reference: str) -> VerifiedPayment:
        with http.client() as c:
            r = c.get(
                f"{self.base_url}/transactions/verify_by_reference",
                params={"tx_ref": reference},
                headers=self._headers(),
            )
        body = r.json() if r.content else {}
        if r.status_code >= 500:
            raise PaymentProviderError(f"Flutterwave verify: HTTP {r.status_code}")
        data = body.get("data") or {}
        status = str(data.get("status", body.get("status", "unknown")))
        amount = Decimal(str(data.get("amount") or 0))
        return VerifiedPayment(
            reference=str(data.get("tx_ref", reference)),
            succeeded=status == "successful",
            status=status,
            amount_pesewas=int((amount * 100).to_integral_value()),
            currency=str(data.get("currency", "")),
            provider_transaction_id=str(data.get("id", "")),
            paid_at=parse_datetime(data["created_at"]) if data.get("created_at") else None,
            raw=_safe(data),
        )

    def webhook_is_authentic(self, raw_body: bytes, headers: Any) -> bool:
        received = _header(headers, "verif-hash")
        expected = settings.FLUTTERWAVE_WEBHOOK_HASH
        return bool(expected) and bool(received) and hmac.compare_digest(received, expected)

    def reference_from_webhook(self, payload: dict[str, Any]) -> str | None:
        if payload.get("event") not in {"charge.completed", None}:
            return None
        data = payload.get("data") or payload
        return data.get("tx_ref") or data.get("txRef")


PROVIDERS: dict[str, Provider] = {"paystack": Paystack(), "flutterwave": Flutterwave()}


def provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        raise PaymentProviderError(f"Unknown payment provider {name}") from exc
