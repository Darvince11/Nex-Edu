from __future__ import annotations

from typing import Any

from allauth.account.models import EmailAddress
from allauth.account.signals import (
    email_confirmed,
    password_changed,
    password_reset,
    password_set,
    user_logged_in,
    user_logged_out,
    user_signed_up,
)
from allauth.mfa.signals import authenticator_added, authenticator_removed, authenticator_reset
from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

from .audit import record_platform_event


@receiver(password_reset)
def verify_email_on_password_reset(sender: Any, request: Any, user: Any, **kwargs: Any) -> None:
    """The reset link was emailed to this address, so using it proves ownership."""
    EmailAddress.objects.filter(user=user, email__iexact=user.email).update(verified=True)


# Security events go to the platform audit log (who, when, IP, request ID).
# Credentials are never recorded; a failed sign-in keeps only the email tried.

_ACCOUNT_EVENTS = {
    user_signed_up: "auth.signed_up",
    user_logged_in: "auth.signed_in",
    user_logged_out: "auth.signed_out",
    password_reset: "auth.password_reset",
    password_changed: "auth.password_changed",
    password_set: "auth.password_set",
}


def _account_event(action: str) -> Any:
    def handler(sender: Any, request: Any = None, user: Any = None, **kwargs: Any) -> None:
        if user is not None and getattr(user, "is_authenticated", False):
            record_platform_event(action=action, request=request, actor=user, target=user)

    return handler


_handlers = []  # keep strong references: signals hold receivers weakly
for _signal, _action in _ACCOUNT_EVENTS.items():
    _handler = _account_event(_action)
    _signal.connect(_handler, dispatch_uid=f"platform-audit-{_action}")
    _handlers.append(_handler)


@receiver(email_confirmed, dispatch_uid="platform-audit-email-verified")
def audit_email_verified(sender: Any, request: Any, email_address: Any, **kwargs: Any) -> None:
    record_platform_event(
        action="auth.email_verified",
        request=request,
        actor=email_address.user,
        target=email_address.user,
    )


@receiver(user_login_failed, dispatch_uid="platform-audit-login-failed")
def audit_login_failed(
    sender: Any, credentials: dict[str, Any], request: Any = None, **kwargs: Any
) -> None:
    email = str(credentials.get("email") or credentials.get("username") or "")[:254].lower()
    record_platform_event(action="auth.sign_in_failed", request=request, data={"email": email})


def _mfa_event(action: str) -> Any:
    def handler(sender: Any, request: Any = None, user: Any = None, **kwargs: Any) -> None:
        authenticator = kwargs.get("authenticator")
        record_platform_event(
            action=action,
            request=request,
            actor=user,
            target=user,
            data={"type": getattr(authenticator, "type", "")},
        )

    return handler


for _signal, _action in (
    (authenticator_added, "auth.mfa_added"),
    (authenticator_removed, "auth.mfa_removed"),
    (authenticator_reset, "auth.mfa_reset"),
):
    _handler = _mfa_event(_action)
    _signal.connect(_handler, dispatch_uid=f"platform-audit-{_action}")
    _handlers.append(_handler)
