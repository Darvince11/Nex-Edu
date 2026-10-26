from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from control_plane.audit import record_platform_event
from control_plane.custom_roles import custom_permissions, held_by
from control_plane.forms import clean_person_name
from control_plane.models import Membership, PlatformStaff, Role, Tenant
from control_plane.modules import active_modules
from control_plane.support_access import active_grant
from core.permissions import mfa_enrolled
from core.rbac import grantable_roles, permissions_for_roles
from integrations.phone import normalize_gh_phone


class SchoolSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())
    # What these roles allow, from core.rbac; the UI uses it to show or hide actions.
    # The API still checks every request itself.
    permissions = serializers.ListField(child=serializers.CharField())
    # Roles this person may give or block at the school (core.rbac.can_grant).
    grantable_roles = serializers.ListField(child=serializers.CharField())
    # Modules switched on at the school (core.modules); the menu hides the others.
    modules = serializers.ListField(child=serializers.CharField())
    # The school's own roles this person holds, and what they add.
    custom_roles = serializers.ListField(child=serializers.CharField())
    custom_permissions = serializers.ListField(child=serializers.CharField())
    # Until when Nex Edu support may see the school's set-up (the proprietor allowed it).
    support_access_until = serializers.DateTimeField(allow_null=True)


class UnavailableSchoolSerializer(serializers.Serializer):
    """A school the user belongs to that is suspended or closed."""

    slug = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()
    unpaid = serializers.BooleanField(help_text="Suspended for an unpaid invoice")
    purge_after = serializers.DateField(allow_null=True)
    is_owner = serializers.BooleanField()


class MeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    phone = serializers.CharField(allow_blank=True)
    last_login = serializers.DateTimeField(allow_null=True)
    mfa_enrolled = serializers.BooleanField()
    platform_roles = serializers.ListField(child=serializers.CharField())
    schools = SchoolSerializer(many=True)
    unavailable_schools = UnavailableSchoolSerializer(many=True)


class ProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)

    def _name(self, value: str) -> str:
        try:
            return clean_person_name(value)
        except Exception as exc:  # forms.ValidationError -> DRF error
            raise serializers.ValidationError(getattr(exc, "messages", [str(exc)])) from exc

    def validate_first_name(self, value: str) -> str:
        return self._name(value)

    def validate_last_name(self, value: str) -> str:
        return self._name(value)

    def validate_phone(self, value: str) -> str:
        if not value.strip():
            return ""
        normalized = normalize_gh_phone(value)
        if not normalized:
            raise serializers.ValidationError("Enter a valid Ghanaian phone number.")
        return normalized


def me_payload(user: Any) -> dict[str, Any]:
    schools: dict[str, dict[str, Any]] = {}
    memberships = (
        Membership.objects.filter(user=user, is_active=True, tenant__status=Tenant.Status.ACTIVE)
        .select_related("tenant")
        .order_by("tenant__name", "role")
    )
    for m in memberships:
        entry = schools.setdefault(
            m.tenant.slug,
            {
                "slug": m.tenant.slug,
                "name": m.tenant.name,
                "roles": [],
                "modules": sorted(active_modules(m.tenant)),
            },
        )
        entry["roles"].append(m.role)
    tenants = {m.tenant.slug: m.tenant for m in memberships}
    for slug, entry in schools.items():
        custom = custom_permissions(user, tenants[slug])
        entry["custom_roles"] = [r.name for r in held_by(user, tenants[slug])] if custom else []
        entry["custom_permissions"] = sorted(custom)
        entry["permissions"] = sorted(permissions_for_roles(entry["roles"]) | custom)
        entry["grantable_roles"] = grantable_roles(entry["roles"])
        grant = active_grant(tenants[slug])
        entry["support_access_until"] = grant.expires_at if grant else None
    return {
        "id": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "last_login": user.last_login,
        "mfa_enrolled": mfa_enrolled(user),
        "platform_roles": list(
            PlatformStaff.objects.filter(user=user, is_active=True).values_list("role", flat=True)
        ),
        "schools": list(schools.values()),
        "unavailable_schools": _unavailable_schools(user),
    }


def _unavailable_schools(user: Any) -> list[dict[str, Any]]:
    """Suspended or closed schools the user belongs to, so they can be told why
    (and the proprietor can pay or download the export)."""
    rows: dict[str, dict[str, Any]] = {}
    for m in Membership.objects.filter(
        user=user,
        is_active=True,
        tenant__status__in=[Tenant.Status.SUSPENDED, Tenant.Status.OFFBOARDED],
        tenant__purged_at__isnull=True,
    ).select_related("tenant"):
        entry = rows.setdefault(
            m.tenant.slug,
            {
                "slug": m.tenant.slug,
                "name": m.tenant.name,
                "status": m.tenant.status,
                "unpaid": m.tenant.status_reason == "nonpayment",
                "purge_after": m.tenant.purge_after,
                "is_owner": False,
            },
        )
        entry["is_owner"] = entry["is_owner"] or m.role == Role.OWNER
    return list(rows.values())


class MeView(APIView):
    """The signed-in user and the schools they belong to. Needs no school selected.

    PATCH lets people correct their own name and phone; email changes go through
    the school, because the email is how invitations and sign-in reach them.
    """

    permission_classes = [IsAuthenticated]
    tenant_scoped = False

    @extend_schema(responses=MeSerializer)
    def get(self, request: Request) -> Response:
        return Response(MeSerializer(me_payload(request.user)).data)

    @extend_schema(request=ProfileUpdateSerializer, responses=MeSerializer)
    def patch(self, request: Request) -> Response:
        data = ProfileUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        changes = dict(data.validated_data)
        if not changes:
            raise ValidationError("Nothing to change.")
        user: Any = request.user
        for field, value in changes.items():
            setattr(user, field, value)
        user.save(update_fields=list(changes))
        record_platform_event(
            action="account.profile_updated",
            request=request,
            actor=user,
            target=user,
            data={"fields": sorted(changes)},
        )
        return Response(MeSerializer(me_payload(user)).data)
