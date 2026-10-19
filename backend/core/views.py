"""Base classes for tenant API views."""

from __future__ import annotations

from typing import Any

from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.throttling import AnonRateThrottle

from core.permissions import load_membership


class TenantViewSet(viewsets.GenericViewSet):  # type: ignore[type-arg]
    """Every action must appear in ``required_permissions`` (or its HTTP method /
    "SAFE"), otherwise HasRequiredPermission denies it."""

    pagination_class = None

    def actor(self) -> tuple[Any, frozenset[str], frozenset[str]]:
        """(user, roles, permissions) of the caller in the current school."""
        roles = load_membership(self.request)
        return self.request.user, roles, getattr(self.request, "permissions", frozenset())


class PublicThrottle(AnonRateThrottle):
    scope = "public"


class PublicEndpointMixin:
    """For deliberately unauthenticated endpoints (admission form, payment webhooks).

    The authorization guard test accepts a view without ``required_permissions``
    only when it carries this marker.
    """

    public_endpoint = True
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [PublicThrottle]


def query_param(request: Request, name: str) -> str | None:
    value = request.query_params.get(name)
    return value or None
