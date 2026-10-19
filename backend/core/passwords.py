"""Rejects passwords found in public breach corpora (Have I Been Pwned).

Uses the k-anonymity range API: only the first 5 hex characters of the SHA-1
hash leave the server, never the password. If the service is unreachable the
check passes (fail-open) and logs a warning, so an outage can't block logins.
"""

from __future__ import annotations

import hashlib
import logging
import urllib.request
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/"


def breach_count(password: str, *, timeout: float = 2.0) -> int | None:
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    request = urllib.request.Request(  # noqa: S310 - fixed https URL
        HIBP_RANGE_URL + prefix, headers={"Add-Padding": "true", "User-Agent": "nexedu-api"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode()
    except OSError:
        logger.warning("Breached-password check unavailable; allowing password")
        return None
    for line in body.splitlines():
        candidate, _, count = line.partition(":")
        if candidate == suffix:
            return int(count)
    return 0


class BreachedPasswordValidator:
    def validate(self, password: str, user: Any = None) -> None:
        if not settings.BREACHED_PASSWORD_CHECK_ENABLED:
            return
        count = breach_count(password)
        if count:
            raise ValidationError(
                "This password has appeared in a data breach. Choose a different one.",
                code="password_breached",
            )

    def get_help_text(self) -> str:
        return "Your password must not appear in known data breaches."
