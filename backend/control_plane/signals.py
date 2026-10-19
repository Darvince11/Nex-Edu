from __future__ import annotations

from typing import Any

from allauth.account.models import EmailAddress
from allauth.account.signals import password_reset
from django.dispatch import receiver


@receiver(password_reset)
def verify_email_on_password_reset(sender: Any, request: Any, user: Any, **kwargs: Any) -> None:
    """The reset link was emailed to this address, so using it proves ownership."""
    EmailAddress.objects.filter(user=user, email__iexact=user.email).update(verified=True)
