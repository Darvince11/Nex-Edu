"""The canteen. The canteen manager runs the till (sales, plan meals, cash top-ups);
the bursar and school leaders also set the menu, meal plans and refunds; parents
see their children's wallets and can set a daily spending limit."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.api.views import AuditedCrudViewSet
from apps.academics.models import ClassArm
from apps.academics.services import current_term
from apps.students.models import Student, StudentGuardian
from apps.students.selectors import visible_students
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.permissions import load_membership
from core.rbac import Perm

from .. import services
from ..models import MealPlan, MenuItem, Wallet, WalletEntry

VIEW, SELL, MANAGE = Perm.CANTEEN_VIEW, Perm.CANTEEN_SELL, Perm.CANTEEN_MANAGE
TILL = (SELL, MANAGE)


def _perms(request: Request) -> frozenset[str]:
    load_membership(request)
    return getattr(request, "permissions", frozenset())


def _active_pupil(student_id: Any) -> Student:
    return get_object_or_404(
        Student.objects.select_related("arm__level"), pk=student_id, status=Student.Status.ACTIVE
    )


class MenuItemSerializer(serializers.ModelSerializer[MenuItem]):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = MenuItem
        fields: ClassVar = ["id", "name", "kind", "kind_label", "price_pesewas", "is_available"]
        extra_kwargs: ClassVar = {"price_pesewas": {"min_value": 1, "max_value": 100_000}}


class MenuItemViewSet(AuditedCrudViewSet):
    serializer_class = MenuItemSerializer
    audit_name = "menu_item"
    queryset = MenuItem.objects.all()
    required_permissions: ClassVar = {
        "list": (VIEW, SELL, MANAGE),
        "retrieve": (VIEW, SELL, MANAGE),
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
    }


class EntrySerializer(serializers.ModelSerializer[WalletEntry]):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = WalletEntry
        fields: ClassVar = [
            "id",
            "kind",
            "kind_label",
            "amount_pesewas",
            "balance_after_pesewas",
            "items",
            "reference",
            "created_at",
        ]


class TillSearchView(APIView):
    """Pupils to serve, by name or admission number (?q=), with their balance."""

    required_permissions: ClassVar = {"GET": TILL}

    @extend_schema(
        parameters=[OpenApiParameter("q", OpenApiTypes.STR)], responses=OpenApiTypes.OBJECT
    )
    def get(self, request: Request) -> Response:
        q = request.query_params.get("q", "").strip()
        if len(q) < 2:
            return Response([])
        pupils = (
            Student.objects.filter(status=Student.Status.ACTIVE)
            .filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(admission_number__icontains=q)
            )
            .select_related("arm__level", "canteen_wallet")[:15]
        )
        return Response(
            [
                {
                    "student": str(p.pk),
                    "name": p.full_name,
                    "admission_number": p.admission_number,
                    "class": str(p.arm) if p.arm_id else "",
                    "balance_pesewas": getattr(
                        getattr(p, "canteen_wallet", None), "balance_pesewas", 0
                    ),
                }
                for p in pupils
            ]
        )


class SaleSerializer(serializers.Serializer):  # type: ignore[type-arg]
    items = serializers.ListField(child=serializers.DictField(), allow_empty=False)


class AmountSerializer(serializers.Serializer):  # type: ignore[type-arg]
    amount_pesewas = serializers.IntegerField(min_value=1)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class RefundSerializer(serializers.Serializer):  # type: ignore[type-arg]
    amount_pesewas = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=200)


class TillView(APIView):
    """A pupil at the till: balance, today's spending, meal plan."""

    required_permissions: ClassVar = {"GET": TILL}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, student_id: str) -> Response:
        return Response(services.till_view(_active_pupil(student_id)))


class TillActionView(APIView):
    """sell | serve | top_up | refund, for one pupil."""

    required_permissions: ClassVar = {"POST": TILL}

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, student_id: str, what: str) -> Response:
        student = _active_pupil(student_id)
        if what == "sell":
            data = SaleSerializer(data=request.data)
            data.is_valid(raise_exception=True)
            try:
                basket = [
                    {"item": int(b["item"]), "qty": int(b.get("qty", 1))}
                    for b in data.validated_data["items"]
                ]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValidationError({"items": "Each item needs an id and a number."}) from exc
            services.purchase(request=request, student=student, basket=basket)
        elif what == "serve":
            services.serve_on_plan(request=request, student=student)
        elif what == "top_up":
            data = AmountSerializer(data=request.data)
            data.is_valid(raise_exception=True)
            services.top_up(
                request=request,
                student=student,
                amount=data.validated_data["amount_pesewas"],
                reference=data.validated_data["reference"],
            )
        elif what == "refund":
            if MANAGE not in _perms(request):
                raise PermissionDenied("Only the bursar or school leaders give refunds.")
            data = RefundSerializer(data=request.data)
            data.is_valid(raise_exception=True)
            services.refund(
                request=request,
                student=student,
                amount=data.validated_data["amount_pesewas"],
                reason=data.validated_data["reason"],
            )
        else:
            raise ValidationError({"detail": "Unknown till action."})
        return Response(services.till_view(student), status=status.HTTP_201_CREATED)


class WalletRulesSerializer(serializers.ModelSerializer[Wallet]):
    class Meta:
        model = Wallet
        fields: ClassVar = ["daily_limit_pesewas", "low_balance_pesewas"]
        extra_kwargs: ClassVar = {
            "daily_limit_pesewas": {"min_value": 0, "max_value": 100_000},
            "low_balance_pesewas": {"min_value": 0, "max_value": 100_000},
        }


class WalletView(APIView):
    """A pupil's wallet and its history. Parents see (and set limits for) their own
    children; the till and the bursar see everyone's."""

    required_permissions: ClassVar = {"GET": (VIEW, SELL, MANAGE), "PATCH": (VIEW, MANAGE)}

    def _student(self, request: Request, student_id: str) -> Student:
        perms = _perms(request)
        if perms & {SELL, MANAGE}:
            return get_object_or_404(Student, pk=student_id)
        return get_object_or_404(
            visible_students(request.user, load_membership(request), perms), pk=student_id
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, student_id: str) -> Response:
        student = self._student(request, student_id)
        wallet = services.wallet_for(student)
        return Response(
            {
                **services.till_view(student),
                "low_balance_pesewas": wallet.low_balance_pesewas,
                "entries": EntrySerializer(wallet.entries.all()[:50], many=True).data,
            }
        )

    @extend_schema(request=WalletRulesSerializer, responses=WalletRulesSerializer)
    def patch(self, request: Request, student_id: str) -> Response:
        student = self._student(request, student_id)
        if (
            MANAGE not in _perms(request)
            and not StudentGuardian.objects.filter(
                student=student, guardian_user_id=request.user.pk
            ).exists()
        ):
            raise PermissionDenied("Only the pupil's parents or the bursar set these.")
        wallet = services.wallet_for(student)
        data = WalletRulesSerializer(wallet, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        with tenant_atomic():
            data.save()
            record_event(action="canteen.limits", request=request, target=student, after=data.data)
        return Response(data.data)


class MyWalletsView(APIView):
    """Parents and pupils: each child's balance, plan and last purchases."""

    required_permissions: ClassVar = {"GET": VIEW}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        perms = _perms(request)
        if perms & {SELL, MANAGE}:
            return Response([])
        pupils = visible_students(request.user, load_membership(request), perms).filter(
            status=Student.Status.ACTIVE
        )
        out = []
        for student in pupils:
            wallet = services.wallet_for(student)
            out.append(
                {
                    **services.till_view(student),
                    "low_balance_pesewas": wallet.low_balance_pesewas,
                    "entries": EntrySerializer(wallet.entries.all()[:10], many=True).data,
                }
            )
        return Response(out)


class MealPlanView(APIView):
    """This term's meal plans. POST {student} or {arm} adds; DELETE ?student= removes."""

    required_permissions: ClassVar = {"GET": TILL, "POST": MANAGE, "DELETE": MANAGE}

    def _term(self) -> Any:
        term = current_term()
        if term is None:
            raise ValidationError({"detail": "Set the current term first."})
        return term

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        plans = MealPlan.objects.filter(term=self._term()).select_related("student__arm__level")
        return Response(
            [
                {
                    "student": str(p.student_id),
                    "name": p.student.full_name,
                    "class": str(p.student.arm) if p.student.arm_id else "",
                    "note": p.note,
                }
                for p in plans.order_by("student__arm__level__order", "student__last_name")
            ]
        )

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        term = self._term()
        note = str(request.data.get("note", ""))[:120]
        if arm := request.data.get("arm"):
            pupils = list(
                Student.objects.filter(
                    arm=get_object_or_404(ClassArm, pk=arm), status=Student.Status.ACTIVE
                )
            )
        else:
            pupils = [_active_pupil(request.data.get("student"))]
        added = 0
        with tenant_atomic():
            for pupil in pupils:
                _, made = MealPlan.objects.get_or_create(
                    student=pupil, term=term, defaults={"note": note}
                )
                added += made
            record_event(action="canteen.plans_added", request=request, after={"pupils": added})
        return Response({"added": added}, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[OpenApiParameter("student", OpenApiTypes.UUID)], responses={204: None}
    )
    def delete(self, request: Request) -> Response:
        MealPlan.objects.filter(
            term=self._term(), student_id=request.query_params.get("student")
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CanteenSummaryView(APIView):
    required_permissions: ClassVar = {"GET": TILL}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(services.day_summary())
