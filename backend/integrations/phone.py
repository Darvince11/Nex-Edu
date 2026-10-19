"""Ghanaian mobile numbers in E.164 (+233...)."""

from __future__ import annotations

import re

_DIGITS = re.compile(r"\D+")

# Mobile network prefixes after the leading 0: MTN (24, 25, 53, 54, 55, 59),
# Telecel (20, 50), AirtelTigo (26, 27, 56, 57), and others in the 2x/5x ranges.
_MOBILE_FIRST_DIGITS = ("2", "5")


def normalize_gh_phone(raw: str | None) -> str | None:
    """'024 412 3456', '+233 24 412 3456' and '233244123456' → '+233244123456'.

    Returns None for anything that isn't a plausible Ghanaian mobile number.
    """
    if not raw:
        return None
    digits = _DIGITS.sub("", raw)
    if digits.startswith("233") and len(digits) == 12:
        national = digits[3:]
    elif digits.startswith("0") and len(digits) == 10:
        national = digits[1:]
    elif len(digits) == 9:
        national = digits
    else:
        return None
    if not national.startswith(_MOBILE_FIRST_DIGITS):
        return None
    return f"+233{national}"
