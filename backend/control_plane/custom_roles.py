"""A school's own roles: named sets of extra permissions for staff members.

- Only the proprietor (``members.manage``) creates, changes, gives and removes them.
- They hold only permissions from ``core.rbac.CUSTOM_ROLE_PERMISSIONS``.
- Only active staff members can hold one; a custom role never lets anyone into a
  school or turns a parent into staff.
- Which records a permission reaches still follows the person's own role (a
  teacher's own classes), except ``students.view_all``, which widens it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db import IntegrityError, transaction
from django.http import HttpRequest
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.audit.services import record_event
from core.rbac import CUSTOM_ROLE_PERMISSIONS, STAFF_ROLES

from .models import CustomRole, CustomRoleGrant, Membership, Tenant, User
from .tenancy import tenant_atomic


def custom_permissions(user: Any, tenant: Tenant) -> frozenset[str]:
    """Extra permissions from the custom roles ``user`` holds at ``tenant``.

    Only counts while the person is active staff there, and only permissions still
    in the catalogue (one removed from it later stops working at once).
    """
    if not is_active_staff(user, tenant):
        return frozenset()
    granted: set[str] = set()
    for perms in CustomRoleGrant.objects.filter(user=user, role__tenant=tenant).values_list(
        "role__permissions", flat=True
    ):
        granted.update(perms or [])
    return frozenset(granted) & frozenset(CUSTOM_ROLE_PERMISSIONS)


def held_by(user: Any, tenant: Tenant) -> list[CustomRole]:
    return list(CustomRole.objects.filter(tenant=tenant, grants__user=user))


def is_active_staff(user: Any, tenant: Tenant) -> bool:
    return Membership.objects.filter(
        user=user, tenant=tenant, is_active=True, role__in=STAFF_ROLES
    ).exists()


def clean_permissions(permissions: Iterable[str]) -> list[str]:
    chosen = sorted(set(permissions))
    unknown = [p for p in chosen if p not in CUSTOM_ROLE_PERMISSIONS]
    if unknown:
        raise ValidationError({"permissions": f"These can't go in a custom role: {unknown}."})
    if not chosen:
        raise ValidationError({"permissions": "Choose at least one thing this role can do."})
    return chosen


def _snapshot(role: CustomRole) -> dict[str, Any]:
    return {"name": role.name, "permissions": list(role.permissions)}


def save_role(
    *,
    request: HttpRequest,
    tenant: Tenant,
    role: CustomRole | None,
    name: str,
    description: str,
    permissions: Iterable[str],
) -> CustomRole:
    perms = clean_permissions(permissions)
    name = name.strip()
    if (
        CustomRole.objects.filter(tenant=tenant, name__iexact=name)
        .exclude(pk=getattr(role, "pk", None))
        .exists()
    ):
        raise ValidationError({"name": "There is already a role with this name."})
    before = _snapshot(role) if role else None
    if role is None:
        role = CustomRole(tenant=tenant, created_by=request.user)
    role.name, role.description, role.permissions = name, description.strip(), perms
    role.save()
    with tenant_atomic():
        record_event(
            action="custom_role.updated" if before else "custom_role.created",
            request=request,
            before=before,
            after=_snapshot(role),
        )
    return role


def delete_role(*, request: HttpRequest, role: CustomRole) -> None:
    before = {**_snapshot(role), "holders": role.grants.count()}
    role.delete()
    with tenant_atomic():
        record_event(action="custom_role.deleted", request=request, before=before)


def grant(*, request: HttpRequest, role: CustomRole, user: User) -> CustomRoleGrant:
    if user.pk == request.user.pk:
        raise PermissionDenied("You can't give a role to yourself.")
    if not is_active_staff(user, role.tenant):
        raise ValidationError({"user": "Only active staff members can hold a custom role."})
    try:
        with transaction.atomic():
            given = CustomRoleGrant.objects.create(role=role, user=user, granted_by=request.user)
    except IntegrityError as exc:
        raise ValidationError({"user": "They already have this role."}) from exc
    with tenant_atomic():
        record_event(
            action="custom_role.granted",
            request=request,
            after={"role": role.name, "email": user.email},
        )
    return given


def revoke(*, request: HttpRequest, role: CustomRole, user: User) -> None:
    deleted, _ = CustomRoleGrant.objects.filter(role=role, user=user).delete()
    if deleted:
        with tenant_atomic():
            record_event(
                action="custom_role.revoked",
                request=request,
                before={"role": role.name, "email": user.email},
            )
