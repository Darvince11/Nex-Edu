"""The stores. The store keeper (and the bursar and leaders) keep stock, suppliers and
the equipment register; any member of staff can ask the stores for something."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import Count, F, Q, QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request as DrfRequest
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.api.views import AuditedCrudViewSet
from control_plane.models import User
from core.rbac import Perm
from core.views import TenantViewSet

from .. import services
from ..models import Asset, Item, Movement, Request, Supplier

ASK, MANAGE = Perm.INVENTORY_REQUEST, Perm.INVENTORY_MANAGE


def _names(ids: set[Any]) -> dict[Any, str]:
    return {u.pk: u.get_full_name() or u.email for u in User.objects.filter(pk__in=ids)}


class SupplierSerializer(serializers.ModelSerializer[Supplier]):
    class Meta:
        model = Supplier
        fields: ClassVar = ["id", "name", "phone", "email", "notes"]


class SupplierViewSet(AuditedCrudViewSet):
    serializer_class = SupplierSerializer
    audit_name = "supplier"
    queryset = Supplier.objects.all()
    required_permissions: ClassVar = {
        k: MANAGE for k in ("list", "retrieve", "create", "update", "partial_update", "destroy")
    }


class ItemSerializer(serializers.ModelSerializer[Item]):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    low = serializers.BooleanField(read_only=True)

    class Meta:
        model = Item
        fields: ClassVar = [
            "id",
            "name",
            "category",
            "category_label",
            "unit",
            "reorder_level",
            "in_stock",
            "low",
            "location",
            "is_active",
        ]
        read_only_fields: ClassVar = ["in_stock"]


class StockMovementSerializer(serializers.ModelSerializer[Movement]):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default="")

    class Meta:
        model = Movement
        fields: ClassVar = [
            "id",
            "item",
            "item_name",
            "kind",
            "kind_label",
            "quantity",
            "stock_after",
            "date",
            "supplier",
            "supplier_name",
            "unit_cost_pesewas",
            "issued_to",
            "note",
            "created_at",
        ]


class StockReceiveSerializer(serializers.Serializer):  # type: ignore[type-arg]
    quantity = serializers.IntegerField(min_value=1, max_value=1_000_000)
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(), required=False, allow_null=True
    )
    unit_cost_pesewas = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    date = serializers.DateField(required=False)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class StockIssueSerializer(serializers.Serializer):  # type: ignore[type-arg]
    quantity = serializers.IntegerField(min_value=1, max_value=1_000_000)
    issued_to = serializers.CharField(max_length=120)
    date = serializers.DateField(required=False)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class StockCountSerializer(serializers.Serializer):  # type: ignore[type-arg]
    counted = serializers.IntegerField(min_value=0)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class ItemViewSet(AuditedCrudViewSet):
    """Stock items. Staff browse what the stores keep (to ask for it); the stores
    record what comes in, goes out, and what a stock count finds."""

    serializer_class = ItemSerializer
    audit_name = "stock_item"
    required_permissions: ClassVar = {
        "list": (ASK, MANAGE),
        "retrieve": (ASK, MANAGE),
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
        "receive": MANAGE,
        "issue": MANAGE,
        "count": MANAGE,
        "movements": MANAGE,
    }

    def get_queryset(self) -> QuerySet[Item]:
        _, _, perms = self.actor()
        qs = Item.objects.all()
        if MANAGE not in perms:
            qs = qs.filter(is_active=True)
        params = self.request.query_params
        if q := params.get("q", "").strip():
            qs = qs.filter(name__icontains=q)
        if params.get("low") == "1":
            qs = qs.filter(in_stock__lte=F("reorder_level"))
        if category := params.get("category"):
            qs = qs.filter(category=category)
        return qs

    def perform_destroy(self, instance: Item) -> None:
        if instance.movements.exists():
            raise ValidationError(
                {"detail": "This item has stock history. Mark it not in use instead."}
            )
        super().perform_destroy(instance)

    def _ok(self, item: Item) -> Response:
        item.refresh_from_db()
        return Response(ItemSerializer(item).data)

    @extend_schema(request=StockReceiveSerializer, responses=ItemSerializer)
    @action(detail=True, methods=["post"])
    def receive(self, request: DrfRequest, pk: str | None = None) -> Response:
        item = self.get_object()
        data = StockReceiveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.receive(request=request, item=item, **data.validated_data)
        return self._ok(item)

    @extend_schema(request=StockIssueSerializer, responses=ItemSerializer)
    @action(detail=True, methods=["post"])
    def issue(self, request: DrfRequest, pk: str | None = None) -> Response:
        item = self.get_object()
        data = StockIssueSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.issue(request=request, item=item, **data.validated_data)
        return self._ok(item)

    @extend_schema(request=StockCountSerializer, responses=ItemSerializer)
    @action(detail=True, methods=["post"])
    def count(self, request: DrfRequest, pk: str | None = None) -> Response:
        item = self.get_object()
        data = StockCountSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.count(request=request, item=item, **data.validated_data)
        return self._ok(item)

    @extend_schema(responses=StockMovementSerializer(many=True))
    @action(detail=True, methods=["get"])
    def movements(self, request: DrfRequest, pk: str | None = None) -> Response:
        item = self.get_object()
        return Response(
            StockMovementSerializer(item.movements.select_related("supplier")[:100], many=True).data
        )


class StoresRequestSerializer(serializers.ModelSerializer[Request]):
    item_name = serializers.CharField(source="item.name", read_only=True)
    unit = serializers.CharField(source="item.unit", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    requested_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Request
        fields: ClassVar = [
            "id",
            "item",
            "item_name",
            "unit",
            "quantity",
            "reason",
            "requested_by",
            "requested_by_name",
            "status",
            "status_label",
            "decision_note",
            "created_at",
            "decided_at",
        ]
        read_only_fields: ClassVar = ["requested_by", "status", "decision_note", "decided_at"]
        extra_kwargs: ClassVar = {"quantity": {"min_value": 1, "max_value": 10_000}}

    def get_requested_by_name(self, obj: Request) -> str:
        return str(self.context.get("names", {}).get(obj.requested_by, ""))


class StoresDecisionSerializer(serializers.Serializer):  # type: ignore[type-arg]
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class RequestViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, TenantViewSet):
    """Staff ask the stores; the stores issue or decline. Each person sees their own
    requests; the stores see everyone's."""

    serializer_class = StoresRequestSerializer
    required_permissions: ClassVar = {
        "list": (ASK, MANAGE),
        "create": (ASK, MANAGE),
        "approve": MANAGE,
        "decline": MANAGE,
    }

    def get_queryset(self) -> QuerySet[Request]:
        user, _, perms = self.actor()
        qs = Request.objects.select_related("item")
        if MANAGE not in perms or self.request.query_params.get("mine") == "1":
            qs = qs.filter(requested_by=user.pk)
        if (state := self.request.query_params.get("status")) in Request.Status.values:
            qs = qs.filter(status=state)
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR),
            OpenApiParameter("mine", OpenApiTypes.STR),
        ]
    )
    def list(self, request: DrfRequest, *args: Any, **kwargs: Any) -> Response:
        rows = list(self.get_queryset()[:300])
        context = {"names": _names({r.requested_by for r in rows})}
        return Response(StoresRequestSerializer(rows, many=True, context=context).data)

    def perform_create(self, serializer: Any) -> None:
        from apps.communication.services import notify_users

        req = serializer.save(requested_by=self.request.user.pk)
        if not req.item.is_active:
            req.delete()
            raise ValidationError({"item": "The stores no longer keep this."})
        notify_users(
            services.store_keepers() - {self.request.user.pk},
            kind="inventory",
            title="New stores request",
            body=f"{req.quantity} {req.item.unit} of {req.item.name}"
            + (f": {req.reason}" if req.reason else ""),
            data={"request": str(req.pk)},
        )

    def _decide(self, request: DrfRequest, pk: str | None, approve: bool) -> Response:
        req = get_object_or_404(Request.objects.select_related("item"), pk=pk)
        data = StoresDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.decide(request=request, req=req, approve=approve, note=data.validated_data["note"])
        return Response(
            StoresRequestSerializer(req, context={"names": _names({req.requested_by})}).data
        )

    @extend_schema(request=StoresDecisionSerializer, responses=StoresRequestSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request: DrfRequest, pk: str | None = None) -> Response:
        return self._decide(request, pk, True)

    @extend_schema(request=StoresDecisionSerializer, responses=StoresRequestSerializer)
    @action(detail=True, methods=["post"])
    def decline(self, request: DrfRequest, pk: str | None = None) -> Response:
        return self._decide(request, pk, False)


class AssetSerializer(serializers.ModelSerializer[Asset]):
    condition_label = serializers.CharField(source="get_condition_display", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default="")

    class Meta:
        model = Asset
        fields: ClassVar = [
            "id",
            "tag",
            "name",
            "category",
            "location",
            "assigned_to",
            "condition",
            "condition_label",
            "purchased_on",
            "cost_pesewas",
            "supplier",
            "supplier_name",
            "notes",
        ]


class AssetViewSet(AuditedCrudViewSet):
    serializer_class = AssetSerializer
    audit_name = "asset"
    required_permissions: ClassVar = {
        k: MANAGE for k in ("list", "retrieve", "create", "update", "partial_update", "destroy")
    }

    def get_queryset(self) -> QuerySet[Asset]:
        qs = Asset.objects.select_related("supplier")
        if q := self.request.query_params.get("q", "").strip():
            qs = qs.filter(Q(tag__icontains=q) | Q(name__icontains=q) | Q(location__icontains=q))
        if (condition := self.request.query_params.get("condition")) in Asset.Condition.values:
            qs = qs.filter(condition=condition)
        return qs


class StoresSummaryView(APIView):
    required_permissions: ClassVar = {"GET": MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: DrfRequest) -> Response:
        low = Item.objects.filter(
            is_active=True, in_stock__lte=F("reorder_level"), reorder_level__gt=0
        )
        return Response(
            {
                "items": Item.objects.filter(is_active=True).count(),
                "low": ItemSerializer(low[:20], many=True).data,
                "low_count": low.count(),
                "waiting": Request.objects.filter(status=Request.Status.PENDING).count(),
                "assets": dict(Asset.objects.values_list("condition").annotate(n=Count("pk"))),
            }
        )
