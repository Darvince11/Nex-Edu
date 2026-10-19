from __future__ import annotations

from allauth.account.adapter import DefaultAccountAdapter
from django.http import HttpRequest


class InviteOnlyAccountAdapter(DefaultAccountAdapter):
    """Schools invite their users. There is no public self-signup."""

    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return False
