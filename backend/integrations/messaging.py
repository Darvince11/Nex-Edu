"""Outbound SMS, WhatsApp and email providers.

Providers are platform-level (one Arkesel account, one WhatsApp Business number),
chosen by settings. Each returns the provider's message id or raises
``DeliveryError``.
"""

from __future__ import annotations

import logging
from typing import Protocol

from django.conf import settings
from django.core.mail import EmailMessage

from . import http

logger = logging.getLogger(__name__)


class DeliveryError(RuntimeError):
    pass


class Sender(Protocol):
    name: str

    def send(self, *, to: str, body: str, subject: str = "", sender_id: str = "") -> str: ...


class ConsoleSender:
    """Development: log instead of sending."""

    def __init__(self, name: str) -> None:
        self.name = name

    def send(self, *, to: str, body: str, subject: str = "", sender_id: str = "") -> str:
        logger.info("[%s to %s] %s %s", self.name, to, subject, body)
        return f"console-{abs(hash((to, body))) % 10**10}"


class ArkeselSms:
    """Arkesel (https://developers.arkesel.com), a Ghanaian SMS gateway."""

    name = "arkesel"

    def send(self, *, to: str, body: str, subject: str = "", sender_id: str = "") -> str:
        payload = {
            "sender": (sender_id or settings.SMS_DEFAULT_SENDER_ID)[:11],
            "message": body,
            "recipients": [to.lstrip("+")],
        }
        with http.client() as c:
            response = c.post(
                f"{settings.ARKESEL_BASE_URL}/api/v2/sms/send",
                json=payload,
                headers={"api-key": settings.ARKESEL_API_KEY},
            )
        if response.status_code >= 400:
            raise DeliveryError(f"Arkesel HTTP {response.status_code}: {response.text[:200]}")
        data = response.json()
        if data.get("status") != "success":
            raise DeliveryError(
                f"Arkesel rejected the message: {str(data.get('message', ''))[:200]}"
            )
        sent = data.get("data") or [{}]
        return str(sent[0].get("id", ""))


class WhatsAppCloud:
    """WhatsApp Business Cloud API. Business-initiated messages must use an
    approved template; ours has one body parameter that carries the text."""

    name = "whatsapp"

    def send(self, *, to: str, body: str, subject: str = "", sender_id: str = "") -> str:
        url = (
            f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
            f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": to.lstrip("+"),
            "type": "template",
            "template": {
                "name": settings.WHATSAPP_TEMPLATE_NAME,
                "language": {"code": "en"},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": body}]}],
            },
        }
        with http.client() as c:
            response = c.post(
                url, json=payload, headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}
            )
        if response.status_code >= 400:
            raise DeliveryError(f"WhatsApp HTTP {response.status_code}: {response.text[:200]}")
        messages = response.json().get("messages") or [{}]
        return str(messages[0].get("id", ""))


class DjangoEmail:
    name = "email"

    def send(self, *, to: str, body: str, subject: str = "", sender_id: str = "") -> str:
        sent = EmailMessage(
            subject=subject or "Message from your school", body=body, to=[to]
        ).send()
        if not sent:
            raise DeliveryError("Email backend did not accept the message")
        return "email"


def sender_for(channel: str) -> Sender:
    if channel == "email":
        return DjangoEmail()
    if channel == "sms":
        return ArkeselSms() if settings.SMS_PROVIDER == "arkesel" else ConsoleSender("sms")
    if channel == "whatsapp":
        return (
            WhatsAppCloud() if settings.WHATSAPP_PROVIDER == "cloud" else ConsoleSender("whatsapp")
        )
    raise ValueError(f"Unknown channel {channel}")
