"""Super Admin (platform) API. Never tenant-scoped; guarded by ``IsPlatformStaff``."""

from __future__ import annotations

from typing import ClassVar

from django.db.models import QuerySet
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from control_plane.models import PlatformRole, Tenant
from core.permissions import IsPlatformStaff


class PlatformTenantSerializer(serializers.ModelSerializer[Tenant]):
    class Meta:
        model = Tenant
        fields: ClassVar = ["id", "slug", "name", "status", "is_canary", "created_at"]


class PlatformTenantListView(generics.ListAPIView[Tenant]):
    """Every school on the platform: metadata only, never school records."""

    permission_classes = [IsAuthenticated, IsPlatformStaff]
    tenant_scoped = False
    platform_roles = (PlatformRole.SUPER_ADMIN, PlatformRole.SUPPORT)
    serializer_class = PlatformTenantSerializer

    def get_queryset(self) -> QuerySet[Tenant]:
        queryset = Tenant.objects.order_by("-created_at")
        status = self.request.query_params.get("status")
        if status in Tenant.Status.values:
            queryset = queryset.filter(status=status)
        return queryset
