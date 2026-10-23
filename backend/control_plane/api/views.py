from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from control_plane.models import Membership, PlatformStaff, Tenant
from core.permissions import mfa_enrolled


class SchoolSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())


class MeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    mfa_enrolled = serializers.BooleanField()
    platform_roles = serializers.ListField(child=serializers.CharField())
    schools = SchoolSerializer(many=True)


class MeView(APIView):
    """The signed-in user and the schools they belong to. Needs no school selected."""

    permission_classes = [IsAuthenticated]
    tenant_scoped = False

    @extend_schema(responses=MeSerializer)
    def get(self, request: Request) -> Response:
        user: Any = request.user
        schools: dict[str, dict[str, Any]] = {}
        memberships = (
            Membership.objects.filter(
                user=user, is_active=True, tenant__status=Tenant.Status.ACTIVE
            )
            .select_related("tenant")
            .order_by("tenant__name", "role")
        )
        for m in memberships:
            entry = schools.setdefault(
                m.tenant.slug, {"slug": m.tenant.slug, "name": m.tenant.name, "roles": []}
            )
            entry["roles"].append(m.role)
        data = {
            "id": user.pk,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "mfa_enrolled": mfa_enrolled(user),
            "platform_roles": list(
                PlatformStaff.objects.filter(user=user, is_active=True).values_list(
                    "role", flat=True
                )
            ),
            "schools": list(schools.values()),
        }
        return Response(MeSerializer(data).data)
