"""DRF permission classes. All three run on every endpoint by default (fail closed).

1. ``IsTenantMember``: a school is selected and the user is an active member.
2. ``MFAEnrolledForStaff``: staff roles must have an authenticator app (TOTP) enrolled.
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
    """Attach ``request.roles``, ``request.permissions`` (from the person's roles and
    any custom roles the school gave them) and ``request.custom_permissions``.
    Cached per request."""
    cached = getattr(request, "roles", None)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    tenant = getattr(request, "tenant", None)
    roles: frozenset[str] = frozenset()
    custom: frozenset[str] = frozenset()
    if tenant is not None and request.user and request.user.is_authenticated:
        roles = frozenset(
            Membership.objects.filter(user=request.user, tenant=tenant, is_active=True).values_list(
                "role", flat=True
            )
        )
        if roles:
            from control_plane.custom_roles import custom_permissions

            custom = custom_permissions(request.user, tenant)
    request.roles = roles  # type: ignore[attr-defined]
    request.custom_permissions = custom  # type: ignore[attr-defined]
    request.permissions = permissions_for_roles(roles) | custom  # type: ignore[attr-defined]
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


def mfa_enrolled(user: Any) -> bool:
    """An authenticator app (TOTP) is enrolled; allauth then demands it at every sign-in.

    Only TOTP counts: recovery codes are a backup, not a factor, and no other
    authenticator type is accepted at sign-in.
    """
    return Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()


MFA_ENROLLMENT_REQUIRED = {
    "detail": "Set up an authenticator app to continue.",
    "code": "mfa_enrollment_required",
}


class MFAEnrolledForStaff(BasePermission):
    message = MFA_ENROLLMENT_REQUIRED  # type: ignore[assignment]

    def has_permission(self, request: Request, view: Any) -> bool:
        if getattr(view, "tenant_scoped", True) is False:
            return True
        roles = load_membership(request)
        if not roles & settings.MFA_REQUIRED_ROLES:
            return True
        return mfa_enrolled(request.user)


MODULE_DISABLED = {
    "detail": "This feature is switched off for your school. The proprietor can switch it on "
    "under Settings, Modules.",
    "code": "module_disabled",
}


def active_modules_for(request: Request) -> frozenset[str]:
    """The school's switched-on modules, worked out once per request."""
    cached = getattr(request, "active_modules", None)
    if cached is None:
        from control_plane.modules import active_modules

        tenant = getattr(request, "tenant", None)
        cached = active_modules(tenant) if tenant is not None else frozenset()
        request.active_modules = cached  # type: ignore[attr-defined]
    return cached  # type: ignore[no-any-return]


class ModuleEnabled(BasePermission):
    """Refuses school requests to a module the school has switched off (or isn't
    entitled to). Every school view must belong to a module; one that doesn't is
    refused (fail closed) and the catalogue test fails."""

    message = MODULE_DISABLED  # type: ignore[assignment]

    def has_permission(self, request: Request, view: Any) -> bool:
        if (
            getattr(view, "tenant_scoped", True) is False
            or getattr(request, "tenant", None) is None
        ):
            return True  # not a school request; other checks handle it
        from core.modules import CORE, module_for_view

        code = module_for_view(view)
        if code is None:
            self.message = "This feature isn't part of any module."  # type: ignore[assignment]
            return False
        return code in CORE or code in active_modules_for(request)


class HasVerifiedEmail(BasePermission):
    """The account's email address has been verified (for actions outside any school,
    such as asking to register one)."""

    message = {  # type: ignore[assignment]
        "detail": "Verify your email address first.",
        "code": "email_unverified",
    }

    def has_permission(self, request: Request, view: Any) -> bool:
        from allauth.account.models import EmailAddress

        user = request.user
        return bool(
            user
            and user.is_authenticated
            and EmailAddress.objects.filter(
                user=user, email__iexact=user.email, verified=True
            ).exists()
        )


class IsPlatformStaff(BasePermission):
    """Platform (Super Admin) endpoints. Needs an active ``PlatformStaff`` row with
    one of the view's ``platform_roles`` (and an authenticator app when
    PLATFORM_MFA_REQUIRED is on). School memberships and ``is_superuser`` count
    for nothing here."""

    message = "This is for Nex Edu platform staff only."

    def has_permission(self, request: Request, view: Any) -> bool:
        from control_plane.models import PlatformStaff

        user = request.user
        if not (user and user.is_authenticated):
            return False
        allowed = getattr(view, "platform_roles", ())
        staff = PlatformStaff.objects.filter(user=user, is_active=True).first()
        if staff is None or staff.role not in allowed:
            return False
        if settings.PLATFORM_MFA_REQUIRED and not mfa_enrolled(user):
            self.message = MFA_ENROLLMENT_REQUIRED  # type: ignore[assignment]
            return False
        return True


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
