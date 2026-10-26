from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import QuerySet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.api.views import AuditedCrudViewSet
from apps.academics.models import ClassArm, ClassLevel, Term
from core.permissions import load_membership
from core.rbac import STAFF_ROLES, Perm, permissions_for_roles
from core.views import PublicEndpointMixin, TenantViewSet
from integrations.payments import PaymentProviderError

from .. import services
from ..models import FeeItem, FeeSchedule, Invoice, InvoiceLine, Payment, Scholarship
from ..pdf import render_receipt
from ..tasks import process_payment_webhook

VIEW, MANAGE = Perm.FINANCE_VIEW, Perm.FINANCE_MANAGE
CONFIG_PERMS: dict[str, Any] = {
    "list": VIEW,
    "retrieve": VIEW,
    "create": MANAGE,
    "update": MANAGE,
    "partial_update": MANAGE,
    "destroy": MANAGE,
}


def _is_finance_staff(request: Request) -> bool:
    """Finance visibility from staff roles (and custom roles, which only staff hold);
    a head teacher who is also a parent still sees every invoice, a parent-only user
    sees their children's."""
    roles = load_membership(request)
    return VIEW in permissions_for_roles(roles & STAFF_ROLES) or VIEW in getattr(
        request, "custom_permissions", frozenset()
    )


class FeeItemSerializer(serializers.ModelSerializer[FeeItem]):
    class Meta:
        model = FeeItem
        fields: ClassVar = ["id", "name", "description", "is_active"]


class FeeScheduleSerializer(serializers.ModelSerializer[FeeSchedule]):
    item_name = serializers.CharField(source="item.name", read_only=True)
    level_name = serializers.CharField(source="level.name", read_only=True, default=None)

    class Meta:
        model = FeeSchedule
        fields: ClassVar = [
            "id",
            "term",
            "level",
            "level_name",
            "item",
            "item_name",
            "amount_pesewas",
            "is_optional",
        ]


class FeeItemViewSet(AuditedCrudViewSet):
    serializer_class = FeeItemSerializer
    audit_name = "finance.fee_item"
    required_permissions: ClassVar = CONFIG_PERMS

    def get_queryset(self) -> QuerySet[FeeItem]:
        return FeeItem.objects.all().order_by("name")


class FeeScheduleViewSet(AuditedCrudViewSet):
    serializer_class = FeeScheduleSerializer
    audit_name = "finance.fee_schedule"
    required_permissions: ClassVar = CONFIG_PERMS

    def get_queryset(self) -> QuerySet[FeeSchedule]:
        qs = FeeSchedule.objects.select_related("item", "level")
        if term := self.request.query_params.get("term"):
            qs = qs.filter(term_id=term)
        return qs.order_by("level__order", "item__name")


class InvoiceLineSerializer(serializers.ModelSerializer[InvoiceLine]):
    class Meta:
        model = InvoiceLine
        fields: ClassVar = ["id", "description", "amount_pesewas"]


class PaymentSerializer(serializers.ModelSerializer[Payment]):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    student_name = serializers.CharField(source="invoice.student.full_name", read_only=True)

    class Meta:
        model = Payment
        fields: ClassVar = [
            "id",
            "invoice",
            "invoice_number",
            "student_name",
            "method",
            "status",
            "amount_pesewas",
            "amount_received_pesewas",
            "reference",
            "receipt_number",
            "authorization_url",
            "paid_at",
            "created_at",
            "note",
        ]


class InvoiceSerializer(serializers.ModelSerializer[Invoice]):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    term_label = serializers.CharField(source="term.__str__", read_only=True)
    balance_pesewas = serializers.IntegerField(read_only=True)
    lines = InvoiceLineSerializer(many=True, read_only=True)
    payments = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields: ClassVar = [
            "id",
            "number",
            "student",
            "student_name",
            "admission_number",
            "term",
            "term_label",
            "status",
            "total_pesewas",
            "paid_pesewas",
            "balance_pesewas",
            "due_date",
            "issued_at",
            "lines",
            "payments",
        ]

    def get_payments(self, obj: Invoice) -> list[dict[str, Any]]:
        done = [p for p in obj.payments.all() if p.status == Payment.Status.SUCCESS]
        return PaymentSerializer(done, many=True).data  # type: ignore[return-value]


class GenerateSerializer(serializers.Serializer):  # type: ignore[type-arg]
    term = serializers.IntegerField()
    level = serializers.IntegerField(required=False, allow_null=True)
    arm = serializers.UUIDField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)


class PaySerializer(serializers.Serializer):  # type: ignore[type-arg]
    provider = serializers.ChoiceField(choices=["paystack", "flutterwave"], default="paystack")
    amount_pesewas = serializers.IntegerField(required=False, allow_null=True, min_value=100)
    email = serializers.EmailField(required=False)


class ManualPaymentSerializer(serializers.Serializer):  # type: ignore[type-arg]
    amount_pesewas = serializers.IntegerField(min_value=1)
    method = serializers.ChoiceField(choices=["cash", "bank_transfer", "pos"])
    reference = serializers.CharField(max_length=60, required=False, default="", allow_blank=True)
    note = serializers.CharField(max_length=200, required=False, default="", allow_blank=True)
    paid_at = serializers.DateTimeField(required=False, allow_null=True)


class DiscountSerializer(serializers.Serializer):  # type: ignore[type-arg]
    description = serializers.CharField(max_length=120)
    amount_pesewas = serializers.IntegerField(min_value=1)


class ReasonSerializer(serializers.Serializer):  # type: ignore[type-arg]
    reason = serializers.CharField(max_length=300)


class InvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantViewSet):
    serializer_class = InvoiceSerializer
    required_permissions: ClassVar = {
        "list": VIEW,
        "retrieve": VIEW,
        "generate": MANAGE,
        "void": MANAGE,
        "discount": MANAGE,
        "record_payment": MANAGE,
        "pay": (Perm.FINANCE_PAY, MANAGE),
    }

    def get_queryset(self) -> QuerySet[Invoice]:
        user, _, _ = self.actor()
        qs = Invoice.objects.select_related("student", "term__session").prefetch_related(
            "lines", "payments"
        )
        if not _is_finance_staff(self.request):
            qs = qs.filter(student__guardians__guardian_user_id=user.pk).distinct()
        params = self.request.query_params
        if term := params.get("term"):
            qs = qs.filter(term_id=term)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        if student := params.get("student"):
            qs = qs.filter(student_id=student)
        if arm := params.get("arm"):
            qs = qs.filter(student__arm_id=arm)
        return qs

    @action(detail=False, methods=["post"])
    def generate(self, request: Request) -> Response:
        data = GenerateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        result = services.generate_invoices(
            request=request,
            term=get_object_or_404(Term, pk=v["term"]),
            level=get_object_or_404(ClassLevel, pk=v["level"]) if v.get("level") else None,
            arm=get_object_or_404(ClassArm, pk=v["arm"]) if v.get("arm") else None,
            due_date=v.get("due_date"),
        )
        return Response(result, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def void(self, request: Request, pk: str | None = None) -> Response:
        data = ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        invoice = services.void_invoice(
            request=request, invoice=self.get_object(), reason=data.validated_data["reason"]
        )
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"])
    def discount(self, request: Request, pk: str | None = None) -> Response:
        data = DiscountSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        invoice = services.add_discount(
            request=request, invoice=self.get_object(), **data.validated_data
        )
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"])
    def record_payment(self, request: Request, pk: str | None = None) -> Response:
        data = ManualPaymentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payment = services.record_manual_payment(
            request=request, invoice=self.get_object(), **data.validated_data
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def pay(self, request: Request, pk: str | None = None) -> Response:
        """Start an online payment (mobile money or card). Requires an Idempotency-Key header."""
        invoice = self.get_object()
        user, _, perms = self.actor()
        services.ensure_can_pay(user, perms, invoice)
        data = PaySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        try:
            payment = services.start_online_payment(
                request=request,
                invoice=invoice,
                provider_name=v["provider"],
                amount_pesewas=v.get("amount_pesewas"),
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                email=v.get("email") or user.email,
            )
        except PaymentProviderError:
            return Response(
                {"detail": "The payment provider is unavailable. Try again shortly."}, status=502
            )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantViewSet):
    serializer_class = PaymentSerializer
    required_permissions: ClassVar = {
        "list": VIEW,
        "retrieve": VIEW,
        "receipt": VIEW,
        "verify": (Perm.FINANCE_PAY, MANAGE),
    }

    def get_queryset(self) -> QuerySet[Payment]:
        user, _, _ = self.actor()
        qs = Payment.objects.select_related("invoice__student", "invoice__term")
        if not _is_finance_staff(self.request):
            qs = qs.filter(invoice__student__guardians__guardian_user_id=user.pk).distinct()
        params = self.request.query_params
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        if reference := params.get("reference"):
            qs = qs.filter(reference=reference)
        if term := params.get("term"):
            qs = qs.filter(invoice__term_id=term)
        return qs

    @action(detail=True, methods=["get"])
    def receipt(self, request: Request, pk: str | None = None) -> HttpResponse:
        payment = self.get_object()
        if payment.status != Payment.Status.SUCCESS:
            raise PermissionDenied("There is no receipt for an unsuccessful payment.")
        response = HttpResponse(render_receipt(payment), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{payment.receipt_number}.pdf"'
        return response

    @action(detail=True, methods=["post"])
    def verify(self, request: Request, pk: str | None = None) -> Response:
        """Called by the payment-return page; checks status with the provider now."""
        try:
            payment = services.verify_payment(self.get_object())
        except PaymentProviderError:
            return Response({"detail": "Couldn't reach the payment provider."}, status=502)
        return Response(PaymentSerializer(payment).data)


class TermSummaryView(APIView):
    required_permissions: ClassVar = {"GET": MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        term = get_object_or_404(Term, pk=request.query_params.get("term"))
        return Response(services.term_summary(term))


class _WebhookView(PublicEndpointMixin, APIView):
    """Signature checked here; crediting happens on the payments queue after a
    fresh verify call to the provider."""

    provider_name = ""
    tenant_scoped = False
    throttle_classes: list[Any] = []

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        raw = request.body
        from integrations.payments import provider

        if not provider(self.provider_name).webhook_is_authentic(raw, request.headers):
            return Response({"detail": "Invalid signature"}, status=401)
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() in {"x-paystack-signature", "verif-hash"}
        }
        process_payment_webhook.delay(self.provider_name, raw.decode(), headers)
        return Response({"received": True})


class PaystackWebhookView(_WebhookView):
    provider_name = "paystack"


class FlutterwaveWebhookView(_WebhookView):
    provider_name = "flutterwave"


# --- Reports and scholarships ------------------------------------------------------------


def _finance_staff_only(request: Request) -> None:
    """Parents hold finance.view for their own invoices; school-wide figures are staff-only."""
    from core.rbac import STAFF_ROLES

    if not load_membership(request) & STAFF_ROLES:
        raise PermissionDenied("Finance reports are for school staff.")


class BalancesReportView(APIView):
    """Pupils who still owe for a term (?term=, default current; ?arm=; ?export=csv)."""

    required_permissions: ClassVar = {"GET": Perm.FINANCE_VIEW}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Any:
        from django.http import HttpResponse

        from .. import reports

        _finance_staff_only(request)
        term_id = request.query_params.get("term")
        term = (
            get_object_or_404(Term, pk=term_id)
            if term_id
            else Term.objects.filter(is_current=True).first()
        )
        if term is None:
            return Response({"detail": "Set a current term first."}, status=400)
        report = reports.balances(term, arm=request.query_params.get("arm") or None)
        if request.query_params.get("export") == "csv":
            response = HttpResponse(
                reports.balances_csv(report), content_type="text/csv; charset=utf-8"
            )
            response["Content-Disposition"] = (
                f'attachment; filename="outstanding-fees-{term.pk}.csv"'
            )
            return response
        return Response(report)


class CollectionsReportView(APIView):
    """Money received between ?start= and ?end= (default: this month so far)."""

    required_permissions: ClassVar = {"GET": Perm.FINANCE_VIEW}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        import datetime as dt

        from django.utils import timezone

        from .. import reports

        _finance_staff_only(request)
        today = timezone.localdate()
        try:
            start = dt.date.fromisoformat(
                request.query_params.get("start") or today.replace(day=1).isoformat()
            )
            end = dt.date.fromisoformat(request.query_params.get("end") or today.isoformat())
        except ValueError:
            return Response({"detail": "Use YYYY-MM-DD dates."}, status=400)
        if end < start or (end - start).days > 366:
            return Response({"detail": "Choose up to a year, ending after it starts."}, status=400)
        return Response(reports.collections(start, end))


class ScholarshipSerializer(serializers.ModelSerializer[Scholarship]):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    student_class = serializers.SerializerMethodField()
    item_name = serializers.CharField(source="item.name", read_only=True, default="")
    apply_now = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Scholarship
        fields: ClassVar = [
            "id",
            "student",
            "student_name",
            "student_class",
            "name",
            "percent",
            "amount_pesewas",
            "item",
            "item_name",
            "is_active",
            "note",
            "created_at",
            "apply_now",
        ]
        read_only_fields: ClassVar = ["created_at"]

    def get_student_class(self, obj: Scholarship) -> str:
        return str(obj.student.arm) if obj.student.arm_id else ""

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        percent = attrs.get("percent", getattr(self.instance, "percent", None))
        amount = attrs.get("amount_pesewas", getattr(self.instance, "amount_pesewas", None))
        if (percent is None) == (amount is None):
            raise serializers.ValidationError("Give either a percentage or an amount.")
        if percent is not None and not (0 < percent <= 100):
            raise serializers.ValidationError({"percent": "Between 1 and 100."})
        return attrs


class ScholarshipViewSet(AuditedCrudViewSet):
    """Standing reductions on pupils' fees. ``apply_now`` on create also takes it off
    the pupil's open invoice for the current term."""

    serializer_class = ScholarshipSerializer
    audit_name = "finance.scholarship"
    required_permissions: ClassVar = {
        "list": Perm.FINANCE_VIEW,
        "retrieve": Perm.FINANCE_VIEW,
        "create": Perm.FINANCE_MANAGE,
        "update": Perm.FINANCE_MANAGE,
        "partial_update": Perm.FINANCE_MANAGE,
        "destroy": Perm.FINANCE_MANAGE,
    }

    def get_queryset(self) -> QuerySet[Scholarship]:
        if getattr(self, "swagger_fake_view", False):  # schema generation
            return Scholarship.objects.none()
        _finance_staff_only(self.request)
        qs = Scholarship.objects.select_related("student__arm__level", "item")
        if student := self.request.query_params.get("student"):
            qs = qs.filter(student_id=student)
        return qs

    def perform_create(self, serializer: Any) -> None:
        apply_now = serializer.validated_data.pop("apply_now", False)
        serializer.validated_data["created_by"] = self.request.user.pk
        super().perform_create(serializer)
        if apply_now:
            scholarship = serializer.instance
            invoice = (
                Invoice.objects.filter(student=scholarship.student, term__is_current=True)
                .exclude(status=Invoice.Status.VOID)
                .first()
            )
            if invoice and invoice.balance_pesewas:
                lines = [
                    (line.item_id, line.amount_pesewas)
                    for line in invoice.lines.filter(amount_pesewas__gt=0)
                ]
                off = min(scholarship.deduction(lines), invoice.balance_pesewas)
                if off:
                    services.add_discount(
                        request=self.request,
                        invoice=invoice,
                        description=f"Scholarship: {scholarship.name}",
                        amount_pesewas=off,
                    )
