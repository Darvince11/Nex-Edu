"""Super Admin (platform) API. Never tenant-scoped; guarded by ``IsPlatformStaff``."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from control_plane.audit import record_platform_event
from control_plane.models import PlatformRole, SchoolRegistration, Tenant
from control_plane.registrations import reject_registration, retry_setup, start_approval
from control_plane.tasks import provision_registration
from control_plane.usage import overview, school_detail, school_rows
from core.permissions import IsPlatformStaff
from core.tasks import enqueue_after_commit

logger = logging.getLogger(__name__)

READERS = (PlatformRole.SUPER_ADMIN, PlatformRole.SUPPORT)
DECIDERS = (PlatformRole.SUPER_ADMIN,)


class PlatformTenantSerializer(serializers.ModelSerializer[Tenant]):
    class Meta:
        model = Tenant
        fields: ClassVar = ["id", "slug", "name", "status", "is_canary", "created_at"]


class PlatformTenantListView(generics.ListAPIView[Tenant]):
    """Every school on the platform: metadata and totals (pupils, staff, price band,
    last activity). Never school records. ?status= and ?q= (name or address) filter."""

    permission_classes = [IsAuthenticated, IsPlatformStaff]
    tenant_scoped = False
    platform_roles = READERS
    serializer_class = PlatformTenantSerializer

    def get_queryset(self) -> QuerySet[Tenant]:
        queryset = Tenant.objects.order_by("-created_at")
        params = self.request.query_params
        if (status := params.get("status")) in Tenant.Status.values:
            queryset = queryset.filter(status=status)
        if q := params.get("q", "").strip():
            queryset = queryset.filter(Q(name__icontains=q) | Q(slug__icontains=q.lower()))
        return queryset

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        ids = [t.pk for t in page] if page is not None else None
        tenants = Tenant.objects.filter(pk__in=ids) if ids is not None else self.get_queryset()
        rows = {row["id"]: row for row in school_rows(tenants)}
        ordered = [rows[pk] for pk in ids] if ids is not None else list(rows.values())
        return self.get_paginated_response(ordered) if page is not None else Response(ordered)


class PlatformOverviewView(APIView):
    """The console dashboard: totals and trends across every school. Billing staff
    see it too (it is mostly money and size); school detail stays with support."""

    permission_classes = [IsAuthenticated, IsPlatformStaff]
    tenant_scoped = False
    platform_roles = (*READERS, PlatformRole.BILLING)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(overview())


class PlatformTenantDetailView(APIView):
    """One school: owner, size, usage, price band and Nex Edu staff actions on it.
    POST refreshes the figures from the school's database now."""

    permission_classes = [IsAuthenticated, IsPlatformStaff]
    tenant_scoped = False
    platform_roles = READERS

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, slug: str) -> Response:
        return Response(school_detail(get_object_or_404(Tenant, slug=slug)))

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, slug: str) -> Response:
        tenant = get_object_or_404(Tenant, slug=slug)
        if tenant.status != Tenant.Status.ACTIVE:
            return Response({"detail": "Only active schools have figures to refresh."}, status=400)
        record_platform_event(action="tenant.usage_refreshed", request=request, tenant=tenant)
        return Response(school_detail(tenant, refresh=True))


class PlatformRegistrationSerializer(serializers.ModelSerializer[SchoolRegistration]):
    """What reviewers need, including the duplicate flag applicants never see."""

    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    owner_joined = serializers.DateTimeField(source="owner.date_joined", read_only=True)
    school_type_label = serializers.CharField(source="get_school_type_display", read_only=True)
    region_label = serializers.CharField(source="get_region_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    reviewed_by_email = serializers.EmailField(
        source="reviewed_by.email", read_only=True, default=""
    )
    school_slug = serializers.SlugRelatedField(source="tenant", slug_field="slug", read_only=True)

    class Meta:
        model = SchoolRegistration
        fields: ClassVar = [
            "id",
            "school_name",
            "slug",
            "school_type",
            "school_type_label",
            "region",
            "region_label",
            "town",
            "phone",
            "expected_pupils",
            "status",
            "status_label",
            "possible_duplicate",
            "owner_name",
            "owner_email",
            "owner_joined",
            "review_note",
            "reviewed_by_email",
            "reviewed_at",
            "school_slug",
            "created_at",
        ]
        read_only_fields = fields

    def get_owner_name(self, obj: SchoolRegistration) -> str:
        return obj.owner.get_full_name()


class PlatformRegistrationListView(generics.ListAPIView[SchoolRegistration]):
    permission_classes = [IsAuthenticated, IsPlatformStaff]
    tenant_scoped = False
    platform_roles = READERS
    serializer_class = PlatformRegistrationSerializer

    def get_queryset(self) -> QuerySet[SchoolRegistration]:
        queryset = SchoolRegistration.objects.select_related("owner", "reviewed_by", "tenant")
        status = self.request.query_params.get("status")
        if status in SchoolRegistration.Status.values:
            queryset = queryset.filter(status=status)
        return queryset.order_by("-created_at")


class PlatformRegistrationDetailView(generics.RetrieveAPIView[SchoolRegistration]):
    permission_classes = [IsAuthenticated, IsPlatformStaff]
    tenant_scoped = False
    platform_roles = READERS
    serializer_class = PlatformRegistrationSerializer
    queryset = SchoolRegistration.objects.select_related("owner", "reviewed_by", "tenant")


class DecisionSerializer(serializers.Serializer[Any]):
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class _DecisionView(APIView):
    """Approve or reject. Super admins only; the reviewer is always the signed-in user."""

    permission_classes = [IsAuthenticated, IsPlatformStaff]
    tenant_scoped = False
    platform_roles = DECIDERS

    def registration(self, pk: str) -> SchoolRegistration:
        return get_object_or_404(SchoolRegistration.objects.select_related("owner"), pk=pk)

    def respond(self, registration: SchoolRegistration) -> Response:
        registration.refresh_from_db()
        return Response(PlatformRegistrationSerializer(registration).data)


class PlatformRegistrationApproveView(_DecisionView):
    """Records the approval and starts set-up in the background (202). Creating a
    school's database can take a minute, longer than a web request should wait;
    the console polls the registration until it's approved or failed."""

    @extend_schema(request=DecisionSerializer, responses={202: PlatformRegistrationSerializer})
    def post(self, request: Request, pk: str) -> Response:
        data = DecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        registration = start_approval(
            self.registration(pk), reviewer=request.user, note=data.validated_data["note"]
        )
        enqueue_after_commit(provision_registration, str(registration.pk))
        return Response(PlatformRegistrationSerializer(registration).data, status=202)


class PlatformRegistrationRetryView(_DecisionView):
    """Try a failed set-up again (super admin). Runs in the background like approval."""

    @extend_schema(request=None, responses={202: PlatformRegistrationSerializer})
    def post(self, request: Request, pk: str) -> Response:
        registration = retry_setup(self.registration(pk), reviewer=request.user)
        enqueue_after_commit(provision_registration, str(registration.pk))
        return Response(PlatformRegistrationSerializer(registration).data, status=202)


class PlatformRegistrationRejectView(_DecisionView):
    @extend_schema(request=DecisionSerializer, responses=PlatformRegistrationSerializer)
    def post(self, request: Request, pk: str) -> Response:
        data = DecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        registration = self.registration(pk)
        reject_registration(registration, reviewer=request.user, note=data.validated_data["note"])
        return self.respond(registration)
