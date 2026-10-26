from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.api.views import AuditedCrudViewSet
from core.permissions import has_perm
from core.rbac import Perm
from core.views import TenantViewSet

from .. import services
from ..models import Department, LeaveRequest, StaffAttendance, StaffProfile

STAFF_CRUD: dict[str, Any] = {
    "list": Perm.STAFF_VIEW,
    "retrieve": Perm.STAFF_VIEW,
    "create": Perm.STAFF_MANAGE,
    "update": Perm.STAFF_MANAGE,
    "partial_update": Perm.STAFF_MANAGE,
    "destroy": Perm.STAFF_MANAGE,
}


class StaffSerializer(serializers.ModelSerializer[StaffProfile]):
    department_name = serializers.CharField(source="department.name", read_only=True, default="")

    class Meta:
        model = StaffProfile
        fields: ClassVar = [
            "id",
            "user_id",
            "staff_number",
            "first_name",
            "last_name",
            "gender",
            "phone",
            "email",
            "job_title",
            "department",
            "department_name",
            "qualification",
            "employment_date",
            "is_active",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar = ["user_id", "staff_number", "created_at", "updated_at"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is None or not has_perm(request, Perm.STAFF_MANAGE):
            for name in ("bank_name", "bank_account_name", "bank_account_number"):
                self.fields.pop(name, None)

    def create(self, validated_data: dict[str, Any]) -> StaffProfile:
        validated_data["staff_number"] = services.next_staff_number()
        return super().create(validated_data)


class StaffViewSet(AuditedCrudViewSet):
    """Staff records. Everyone with a staff login appears automatically; leaders add
    staff without a login (cooks, cleaners, security) here too."""

    serializer_class = StaffSerializer
    audit_name = "staff.profile"
    required_permissions: ClassVar = STAFF_CRUD

    def get_queryset(self) -> QuerySet[StaffProfile]:
        if self.action == "list":
            services.ensure_profiles()
        qs = StaffProfile.objects.select_related("department")
        params = self.request.query_params
        if params.get("active") == "1":
            qs = qs.filter(is_active=True)
        if department := params.get("department"):
            qs = qs.filter(department_id=department)
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(staff_number__icontains=q)
                | Q(job_title__icontains=q)
            )
        return qs


class DepartmentSerializer(serializers.ModelSerializer[Department]):
    head_name = serializers.SerializerMethodField()
    staff_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields: ClassVar = ["id", "name", "head", "head_name", "staff_count"]

    def get_head_name(self, obj: Department) -> str:
        return f"{obj.head.first_name} {obj.head.last_name}".strip() if obj.head else ""

    def get_staff_count(self, obj: Department) -> int:
        return obj.staff.filter(is_active=True).count()


class DepartmentViewSet(AuditedCrudViewSet):
    serializer_class = DepartmentSerializer
    audit_name = "staff.department"
    required_permissions: ClassVar = STAFF_CRUD

    def get_queryset(self) -> QuerySet[Department]:
        return Department.objects.select_related("head")


# --- Staff register ------------------------------------------------------------------------


class RegisterEntrySerializer(serializers.Serializer):  # type: ignore[type-arg]
    staff = serializers.UUIDField()
    status = serializers.ChoiceField(choices=StaffAttendance.Status.choices)
    time_in = serializers.TimeField(required=False, allow_null=True)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class StaffRegisterSerializer(serializers.Serializer):  # type: ignore[type-arg]
    date = serializers.DateField()
    entries = RegisterEntrySerializer(many=True, max_length=1000)


def _date(value: str | None) -> dt.date:
    if not value:
        return timezone.localdate()
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({"date": "Use YYYY-MM-DD."}) from exc


class StaffRegisterView(APIView):
    """The daily staff register. GET ?date=; POST {date, entries}. Leaders only."""

    required_permissions: ClassVar = {"GET": Perm.STAFF_MANAGE, "POST": Perm.STAFF_MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        day = _date(request.query_params.get("date"))
        return Response({"date": day, "rows": services.register(day)})

    @extend_schema(request=StaffRegisterSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = StaffRegisterSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        entries = list(data.validated_data["entries"])
        saved = services.save_register(
            request=request, date=data.validated_data["date"], entries=entries
        )
        return Response({"saved": saved, "rows": services.register(data.validated_data["date"])})


class StaffAttendanceSummaryView(APIView):
    """Days present, late, absent and on leave per member of staff.
    ?start=&end= (default: this month so far)."""

    required_permissions: ClassVar = {"GET": Perm.STAFF_MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        today = timezone.localdate()
        start = _date(request.query_params.get("start") or today.replace(day=1).isoformat())
        end = _date(request.query_params.get("end") or today.isoformat())
        return Response(
            {"start": start, "end": end, "rows": services.attendance_summary(start, end)}
        )


# --- Leave -----------------------------------------------------------------------------------


class LeaveSerializer(serializers.ModelSerializer[LeaveRequest]):
    staff_name = serializers.SerializerMethodField()
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    mine = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields: ClassVar = [
            "id",
            "staff",
            "staff_name",
            "kind",
            "kind_label",
            "start",
            "end",
            "days",
            "reason",
            "status",
            "status_label",
            "decision_note",
            "decided_at",
            "created_at",
            "mine",
        ]
        read_only_fields: ClassVar = [
            "staff",
            "days",
            "status",
            "decision_note",
            "decided_at",
            "created_at",
        ]

    def get_staff_name(self, obj: LeaveRequest) -> str:
        return f"{obj.staff.first_name} {obj.staff.last_name}".strip()

    def get_mine(self, obj: LeaveRequest) -> bool:
        request = self.context.get("request")
        return bool(request and obj.staff.user_id == request.user.pk)


class LeaveDecisionSerializer(serializers.Serializer):  # type: ignore[type-arg]
    approve = serializers.BooleanField()
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class LeaveViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, TenantViewSet):
    """Staff ask for leave and see their own requests; leaders (staff.manage) see
    everyone's and decide. ?mine=1 shows only the viewer's own; ?status= filters."""

    serializer_class = LeaveSerializer
    required_permissions: ClassVar = {
        "list": (Perm.LEAVE_REQUEST, Perm.STAFF_MANAGE),
        "create": Perm.LEAVE_REQUEST,
        "decide": Perm.STAFF_MANAGE,
        "cancel": Perm.LEAVE_REQUEST,
    }

    def get_queryset(self) -> QuerySet[LeaveRequest]:
        qs = LeaveRequest.objects.select_related("staff")
        params = self.request.query_params
        if not has_perm(self.request, Perm.STAFF_MANAGE) or params.get("mine") == "1":
            qs = qs.filter(staff__user_id=self.request.user.pk)
        if (wanted := params.get("status")) in LeaveRequest.Status.values:
            qs = qs.filter(status=wanted)
        return qs

    def perform_create(self, serializer: Any) -> None:
        staff = services.profile_of(self.request.user)
        if staff is None:
            services.ensure_profiles()
            staff = services.profile_of(self.request.user)
        if staff is None:
            raise ValidationError("Your staff record couldn't be found. Ask the school office.")
        fields = {
            k: serializer.validated_data[k]
            for k in ("kind", "start", "end", "reason")
            if k in serializer.validated_data
        }
        serializer.instance = services.request_leave(request=self.request, staff=staff, data=fields)

    @extend_schema(request=LeaveDecisionSerializer, responses=LeaveSerializer)
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, pk: str | None = None) -> Response:
        leave = get_object_or_404(LeaveRequest.objects.select_related("staff"), pk=pk)
        data = LeaveDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.decide_leave(request=request, leave=leave, **data.validated_data)
        return Response(LeaveSerializer(leave, context={"request": request}).data)

    @extend_schema(request=None, responses=LeaveSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        leave = get_object_or_404(LeaveRequest.objects.select_related("staff"), pk=pk)
        services.cancel_leave(request=request, leave=leave)
        return Response(
            LeaveSerializer(leave, context={"request": request}).data, status=status.HTTP_200_OK
        )
