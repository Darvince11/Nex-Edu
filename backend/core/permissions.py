"""DRF permission classes. All three run on every endpoint by default (fail closed).

1. ``IsTenantMember``: a school is selected and the user is an active member.
2. ``MFAEnrolledForStaff``: staff roles must have a passkey or TOTP enrolled.
3. ``HasRequiredPermission``: the view declares ``required_permissions`` per
   HTTP method, and the user's roles grant them. A view that forgets to declare
   permissions is denied, not allowed.
"""

from __future__ import annotations

from typing import Any

from allauth.mfa.models import Authenticator
from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request

from control_plane.models import Membership
from core.rbac import permissions_for_roles


def load_membership(request: Request) -> frozenset[str]:
    """Attach ``request.roles`` and ``request.permissions``. Cached per request."""
    cached = getattr(request, "roles", None)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    tenant = getattr(request, "tenant", None)
    roles: frozenset[str] = frozenset()
    if tenant is not None and request.user and request.user.is_authenticated:
        roles = frozenset(
            Membership.objects.filter(user=request.user, tenant=tenant, is_active=True).values_list(
                "role", flat=True
            )
        )
    request.roles = roles  # type: ignore[attr-defined]
    request.permissions = permissions_for_roles(roles)  # type: ignore[attr-defined]
    return roles


class IsTenantMember(BasePermission):
    message = "You are not a member of this school."

    def has_permission(self, request: Request, view: Any) -> bool:
        if getattr(view, "tenant_scoped", True) is False:
            return True
        if getattr(request, "tenant", None) is None:
            self.message = "Select a school first."
            return False
        return bool(load_membership(request))


class MFAEnrolledForStaff(BasePermission):
    message = {  # type: ignore[assignment]
        "detail": "Set up a passkey or authenticator app to continue.",
        "code": "mfa_enrollment_required",
    }

    def has_permission(self, request: Request, view: Any) -> bool:
        if getattr(view, "tenant_scoped", True) is False:
            return True
        roles = load_membership(request)
        if not roles & settings.MFA_REQUIRED_ROLES:
            return True
        return (
            Authenticator.objects.filter(user=request.user)
            .exclude(type=Authenticator.Type.RECOVERY_CODES)
            .exists()
        )


class HasRequiredPermission(BasePermission):
    message = "You do not have permission to do this."

    def has_permission(self, request: Request, view: Any) -> bool:
        if getattr(view, "tenant_scoped", True) is False:
            return True
        needed = required_permission_for(view, request.method or "GET")
        if needed is None:
            return False
        load_membership(request)
        granted = getattr(request, "permissions", frozenset())
        options = (needed,) if isinstance(needed, str) else tuple(needed)
        return any(p in granted for p in options)


def required_permission_for(view: Any, method: str) -> str | tuple[str, ...] | None:
    """Look up what a view needs: viewset action name first, then HTTP method.

    ``required_permissions`` maps an action ("list", "publish", ...) or a method
    ("GET", "POST", or "SAFE" for any read) to one permission or a tuple of
    alternatives. Anything not listed is denied.
    """
    required: dict[str, Any] = getattr(view, "required_permissions", {})
    action = getattr(view, "action", None)
    if action and action in required:
        return required[action]  # type: ignore[no-any-return]
    if method in required:
        return required[method]  # type: ignore[no-any-return]
    if method in SAFE_METHODS:
        return required.get("SAFE")
    return None


def has_perm(request: Request, perm: str) -> bool:
    load_membership(request)
    return perm in getattr(request, "permissions", frozenset())


def roles_of(request: Request) -> frozenset[str]:
    return load_membership(request)
