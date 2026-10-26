"""The school's own roles (proprietor only): what each may do, and who holds it."""

from __future__ import annotations

from typing import Any, ClassVar

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from control_plane import custom_roles
from control_plane.models import CustomRole, Membership, User
from core.rbac import CUSTOM_ROLE_PERMISSIONS, STAFF_ROLES, Perm

MANAGE = Perm.MEMBERS_MANAGE


class CustomRoleSerializer(serializers.Serializer):  # type: ignore[type-arg]
    name = serializers.CharField(max_length=60)
    description = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    permissions = serializers.ListField(child=serializers.CharField(), allow_empty=False)


class HolderSerializer(serializers.Serializer):  # type: ignore[type-arg]
    user = serializers.UUIDField()


def _person(user: User) -> dict[str, str]:
    return {
        "id": str(user.pk),
        "name": user.get_full_name() or user.email.split("@")[0],
        "email": user.email,
    }


def _role(role: CustomRole) -> dict[str, Any]:
    return {
        "id": str(role.pk),
        "name": role.name,
        "description": role.description,
        "permissions": [p for p in role.permissions if p in CUSTOM_ROLE_PERMISSIONS],
        "holders": [_person(g.user) for g in role.grants.select_related("user")],
        "updated_at": role.updated_at,
    }


class CustomRolesView(APIView):
    """GET: the school's roles, what a role may contain, and the staff who can hold
    one. POST: a new role."""

    module = "people"
    required_permissions: ClassVar = {"GET": MANAGE, "POST": MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        tenant = request.tenant  # type: ignore[attr-defined]
        staff_ids = (
            Membership.objects.filter(tenant=tenant, is_active=True, role__in=STAFF_ROLES)
            .values_list("user_id", flat=True)
            .distinct()
        )
        staff = User.objects.filter(pk__in=staff_ids).order_by("last_name", "first_name")
        return Response(
            {
                "roles": [_role(r) for r in CustomRole.objects.filter(tenant=tenant)],
                "catalogue": [
                    {"code": code, "group": group, "label": label}
                    for code, (group, label) in CUSTOM_ROLE_PERMISSIONS.items()
                ],
                "staff": [_person(u) for u in staff],
            }
        )

    @extend_schema(request=CustomRoleSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = CustomRoleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        role = custom_roles.save_role(
            request=request,
            tenant=request.tenant,  # type: ignore[attr-defined]
            role=None,
            **data.validated_data,
        )
        return Response(_role(role), status=status.HTTP_201_CREATED)


class CustomRoleView(APIView):
    """PATCH: rename or change what a role may do. DELETE: remove it from everyone."""

    module = "people"
    required_permissions: ClassVar = {"PATCH": MANAGE, "DELETE": MANAGE}

    def _get(self, request: Request, pk: str) -> CustomRole:
        return get_object_or_404(CustomRole, pk=pk, tenant=request.tenant)  # type: ignore[attr-defined]

    @extend_schema(request=CustomRoleSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request: Request, pk: str) -> Response:
        role = self._get(request, pk)
        data = CustomRoleSerializer(
            data={
                "name": role.name,
                "description": role.description,
                "permissions": role.permissions,
                **request.data,
            }
        )
        data.is_valid(raise_exception=True)
        role = custom_roles.save_role(
            request=request, tenant=role.tenant, role=role, **data.validated_data
        )
        return Response(_role(role))

    @extend_schema(responses={204: None})
    def delete(self, request: Request, pk: str) -> Response:
        custom_roles.delete_role(request=request, role=self._get(request, pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustomRoleHoldersView(APIView):
    """POST {user}: give the role to a staff member. DELETE ?user=: take it away."""

    module = "people"
    required_permissions: ClassVar = {"POST": MANAGE, "DELETE": MANAGE}

    @extend_schema(request=HolderSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, pk: str) -> Response:
        role = get_object_or_404(CustomRole, pk=pk, tenant=request.tenant)  # type: ignore[attr-defined]
        data = HolderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = get_object_or_404(User, pk=data.validated_data["user"])
        custom_roles.grant(request=request, role=role, user=user)
        return Response(_role(role), status=status.HTTP_201_CREATED)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def delete(self, request: Request, pk: str) -> Response:
        role = get_object_or_404(CustomRole, pk=pk, tenant=request.tenant)  # type: ignore[attr-defined]
        holder = HolderSerializer(data={"user": request.query_params.get("user")})
        holder.is_valid(raise_exception=True)
        user = get_object_or_404(User, pk=holder.validated_data["user"])
        custom_roles.revoke(request=request, role=role, user=user)
        return Response(_role(role))
