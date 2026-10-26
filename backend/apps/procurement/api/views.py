"""Procurement. Staff see their own requests; approvers see what needs approving;
the bursar (``procurement.manage``) sees everything and runs orders and payments."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.models import LedgerAccount
from apps.inventory.models import Supplier
from control_plane.models import User
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm
from core.views import TenantViewSet

from .. import services
from ..models import ProcurementSettings, PurchaseOrder, Requisition

ASK, APPROVE, FINAL, MANAGE = (
    Perm.PROCUREMENT_REQUEST,
    Perm.PROCUREMENT_APPROVE,
    Perm.PROCUREMENT_FINAL,
    Perm.PROCUREMENT_MANAGE,
)
ANY = (ASK, APPROVE, FINAL, MANAGE)


def _names(ids: set[Any]) -> dict[Any, str]:
    return {u.pk: u.get_full_name() or u.email for u in User.objects.filter(pk__in=ids)}


class RequisitionSerializer(serializers.ModelSerializer[Requisition]):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    requested_by_name = serializers.SerializerMethodField()
    order_number = serializers.CharField(source="order.number", read_only=True, default="")

    class Meta:
        model = Requisition
        fields: ClassVar = [
            "id",
            "number",
            "purpose",
            "lines",
            "total_pesewas",
            "needed_by",
            "status",
            "status_label",
            "requested_by_name",
            "decision_note",
            "order_number",
            "created_at",
        ]
        read_only_fields: ClassVar = ["number", "total_pesewas", "status", "decision_note"]

    def get_requested_by_name(self, obj: Requisition) -> str:
        return str(self.context.get("names", {}).get(obj.requested_by, ""))


class DecideSerializer(serializers.Serializer):  # type: ignore[type-arg]
    approve = serializers.BooleanField()
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class OrderSerializer(serializers.Serializer):  # type: ignore[type-arg]
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    account = serializers.PrimaryKeyRelatedField(queryset=LedgerAccount.objects.all())


class RequisitionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, TenantViewSet):
    serializer_class = RequisitionSerializer
    required_permissions: ClassVar = {
        "list": ANY,
        "create": ANY,
        "decide": (APPROVE, FINAL),
        "order": MANAGE,
    }

    def get_queryset(self) -> QuerySet[Requisition]:
        user, _, perms = self.actor()
        qs = Requisition.objects.select_related("order")
        if MANAGE in perms:
            pass
        elif perms & {APPROVE, FINAL}:
            waiting = []
            if APPROVE in perms:
                waiting.append(Requisition.Status.SUBMITTED)
            if FINAL in perms:
                waiting.append(Requisition.Status.HEAD_APPROVED)
            qs = qs.filter(
                Q(requested_by=user.pk) | Q(status__in=waiting) | Q(head_approved_by=user.pk)
            )
        else:
            qs = qs.filter(requested_by=user.pk)
        if (state := self.request.query_params.get("status")) in Requisition.Status.values:
            qs = qs.filter(status=state)
        return qs

    @extend_schema(parameters=[OpenApiParameter("status", OpenApiTypes.STR)])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        rows = list(self.get_queryset()[:300])
        return Response(
            RequisitionSerializer(
                rows, many=True, context={"names": _names({r.requested_by for r in rows})}
            ).data
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        data = RequisitionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        req = services.request(
            request=request,
            purpose=data.validated_data["purpose"],
            lines=request.data.get("lines"),
            needed_by=data.validated_data.get("needed_by"),
        )
        return Response(RequisitionSerializer(req).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=DecideSerializer, responses=RequisitionSerializer)
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, pk: str | None = None) -> Response:
        req = get_object_or_404(Requisition, pk=pk)
        data = DecideSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _, _, perms = self.actor()
        services.decide(
            request=request,
            req=req,
            approve=data.validated_data["approve"],
            note=data.validated_data["note"],
            perms=perms,
        )
        return Response(RequisitionSerializer(req).data)

    @extend_schema(request=OrderSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def order(self, request: Request, pk: str | None = None) -> Response:
        req = get_object_or_404(Requisition, pk=pk)
        data = OrderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        po = services.order(request=request, req=req, **data.validated_data)
        return Response(PurchaseOrderSerializer(po).data, status=status.HTTP_201_CREATED)


class PurchaseOrderSerializer(serializers.ModelSerializer[PurchaseOrder]):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    requisition_number = serializers.CharField(source="requisition.number", read_only=True)
    purpose = serializers.CharField(source="requisition.purpose", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields: ClassVar = [
            "id",
            "number",
            "requisition_number",
            "purpose",
            "supplier",
            "supplier_name",
            "account",
            "account_name",
            "lines",
            "total_pesewas",
            "status",
            "status_label",
            "received_on",
            "invoice_reference",
            "paid_on",
            "payment_reference",
            "created_at",
        ]


class ReceiveSerializer(serializers.Serializer):  # type: ignore[type-arg]
    invoice_reference = serializers.CharField(
        max_length=60, required=False, allow_blank=True, default=""
    )
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class PaySerializer(serializers.Serializer):  # type: ignore[type-arg]
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class PurchaseOrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantViewSet):
    serializer_class = PurchaseOrderSerializer
    queryset = PurchaseOrder.objects.select_related("supplier", "account", "requisition")
    required_permissions: ClassVar = {
        "list": MANAGE,
        "retrieve": MANAGE,
        "receive": MANAGE,
        "pay": MANAGE,
    }

    @extend_schema(request=ReceiveSerializer, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"])
    def receive(self, request: Request, pk: str | None = None) -> Response:
        data = ReceiveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        po = services.receive(request=request, po=self.get_object(), **data.validated_data)
        return Response(PurchaseOrderSerializer(po).data)

    @extend_schema(request=PaySerializer, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"])
    def pay(self, request: Request, pk: str | None = None) -> Response:
        data = PaySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        po = services.pay(
            request=request, po=self.get_object(), reference=data.validated_data["reference"]
        )
        return Response(PurchaseOrderSerializer(po).data)


class ProcurementSettingsSerializer(serializers.ModelSerializer[ProcurementSettings]):
    class Meta:
        model = ProcurementSettings
        fields: ClassVar = ["proprietor_above_pesewas"]


class ProcurementSettingsView(APIView):
    """How big a request must be before the proprietor approves it too (proprietor only)."""

    required_permissions: ClassVar = {"GET": ANY, "PATCH": FINAL}

    @extend_schema(responses=ProcurementSettingsSerializer)
    def get(self, request: Request) -> Response:
        return Response(ProcurementSettingsSerializer(ProcurementSettings.load()).data)

    @extend_schema(request=ProcurementSettingsSerializer, responses=ProcurementSettingsSerializer)
    def patch(self, request: Request) -> Response:
        rules = ProcurementSettings.load()
        data = ProcurementSettingsSerializer(rules, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        with tenant_atomic():
            data.save()
            record_event(action="procurement.limit_changed", request=request, after=data.data)
        return Response(data.data)
