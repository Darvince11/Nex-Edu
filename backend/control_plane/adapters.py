from __future__ import annotations

from allauth.account.adapter import DefaultAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    """Sign-up is open, but an account by itself opens nothing.

    School access comes only from a membership, which is created by a school's
    invitation or when platform staff approve a school registration. Everything
    else (verification by code, rate limits, enumeration-safe responses, the
    honeypot) is allauth configured in ``settings.base``.
    """
