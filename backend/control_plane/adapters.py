from __future__ import annotations

from typing import Any

from allauth.account.adapter import DefaultAccountAdapter

from control_plane.audit import record_platform_event


class AccountAdapter(DefaultAccountAdapter):
    """Sign-up is open, but an account by itself opens nothing.

    School access comes only from a membership, which is created by a school's
    invitation or when platform staff approve a school registration. Everything
    else (verification by code, rate limits, enumeration-safe responses, the
    honeypot) is allauth configured in ``settings.base``.
    """

    def send_password_reset_mail(self, user: Any, email: str, context: dict[str, Any]) -> None:
        """Record the request (shown on the console's System page), then send the link.
        Requests for unknown emails get allauth's neutral email and aren't recorded."""
        record_platform_event(
            action="auth.password_reset_requested", request=self.request, target=user
        )
        super().send_password_reset_mail(user, email, context)
