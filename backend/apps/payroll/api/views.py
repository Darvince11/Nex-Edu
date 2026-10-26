"""Payroll. The bursar keeps salaries and prepares each month's pay; only the
proprietor approves it (``payroll.approve``). Every member of staff sees their own
payslips once a run is approved. Salaries are never shown to anyone else."""

from __future__ import annotations

from typing import Any, ClassVar

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.staff.models import StaffProfile
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.permissions import load_membership
from core.rbac import Perm
from core.views import TenantViewSet

from .. import services
from ..models import PayrollSettings, PayRun, Payslip, Salary

MANAGE, APPROVE, SELF = Perm.PAYROLL_MANAGE, Perm.PAYROLL_APPROVE, Perm.PAYROLL_SELF


def _perms(request: Request) -> frozenset[str]:
    load_membership(request)
    return getattr(request, "permissions", frozenset())


class PayrollRulesSerializer(serializers.ModelSerializer[PayrollSettings]):
    class Meta:
        model = PayrollSettings
        fields: ClassVar = [
            "paye_bands",
            "ssnit_employee_percent",
            "ssnit_employer_percent",
            "tier2_percent",
            "ssnit_cap_pesewas",
            "rates_confirmed_at",
        ]
        read_only_fields: ClassVar = ["rates_confirmed_at"]

    def validate_paye_bands(self, value: Any) -> Any:
        return services.validate_bands(value)


class PayrollRulesView(APIView):
    """GET/PATCH the tax and SSNIT rules. Changing them asks for them to be confirmed
    again; POST confirms them (after checking against GRA's table)."""

    required_permissions: ClassVar = {"GET": MANAGE, "PATCH": MANAGE, "POST": MANAGE}

    @extend_schema(responses=PayrollRulesSerializer)
    def get(self, request: Request) -> Response:
        return Response(PayrollRulesSerializer(PayrollSettings.load()).data)

    @extend_schema(request=PayrollRulesSerializer, responses=PayrollRulesSerializer)
    def patch(self, request: Request) -> Response:
        rules = PayrollSettings.load()
        data = PayrollRulesSerializer(rules, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        with tenant_atomic():
            data.save(rates_confirmed_at=None, rates_confirmed_by=None)
            record_event(action="payroll.rules_changed", request=request, after=data.data)
        return Response(PayrollRulesSerializer(rules).data)

    @extend_schema(request=None, responses=PayrollRulesSerializer)
    def post(self, request: Request) -> Response:
        rules = PayrollSettings.load()
        with tenant_atomic():
            rules.rates_confirmed_at, rules.rates_confirmed_by = timezone.now(), request.user.pk
            rules.save(update_fields=["rates_confirmed_at", "rates_confirmed_by"])
            record_event(action="payroll.rules_confirmed", request=request)
        return Response(PayrollRulesSerializer(rules).data)


class LineSerializer(serializers.Serializer):  # type: ignore[type-arg]
    name = serializers.CharField(max_length=60)
    amount_pesewas = serializers.IntegerField(min_value=0, max_value=100_000_000)
    taxable = serializers.BooleanField(required=False, default=True)


class SalarySerializer(serializers.ModelSerializer[Salary]):
    allowances = LineSerializer(many=True, required=False)
    deductions = LineSerializer(many=True, required=False)

    class Meta:
        model = Salary
        fields: ClassVar = [
            "basic_pesewas",
            "allowances",
            "deductions",
            "ssnit_number",
            "tin",
            "on_payroll",
        ]
        extra_kwargs: ClassVar = {"basic_pesewas": {"max_value": 100_000_000}}


class SalariesView(APIView):
    """GET: every active member of staff with their pay and this month's figures.
    PUT ?staff=: set one person's pay."""

    required_permissions: ClassVar = {"GET": MANAGE, "PUT": MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        from apps.staff.services import ensure_profiles

        ensure_profiles()  # everyone with a staff login has a staff record
        rules = PayrollSettings.load()
        out = []
        for staff in StaffProfile.objects.filter(is_active=True).order_by(
            "last_name", "first_name"
        ):
            salary = Salary.objects.filter(staff=staff).first()
            out.append(
                {
                    "staff": str(staff.pk),
                    "name": f"{staff.first_name} {staff.last_name}",
                    "job_title": staff.job_title,
                    "salary": SalarySerializer(salary).data if salary else None,
                    "figures": services.figures(salary, rules)
                    if salary and salary.basic_pesewas
                    else None,
                }
            )
        return Response(out)

    @extend_schema(
        parameters=[OpenApiParameter("staff", OpenApiTypes.UUID, required=True)],
        request=SalarySerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def put(self, request: Request) -> Response:
        staff = get_object_or_404(StaffProfile, pk=request.query_params.get("staff"))
        salary, _ = Salary.objects.get_or_create(staff=staff)
        data = SalarySerializer(salary, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        with tenant_atomic():
            data.save()
            record_event(action="payroll.salary_changed", request=request, target=staff)
        return Response(
            {
                "salary": SalarySerializer(salary).data,
                "figures": services.figures(salary, PayrollSettings.load()),
            }
        )


class PayslipSerializer(serializers.ModelSerializer[Payslip]):
    month = serializers.DateField(source="run.month", read_only=True)

    class Meta:
        model = Payslip
        fields: ClassVar = [
            "id",
            "month",
            "staff",
            "staff_name",
            "basic_pesewas",
            "allowances",
            "gross_pesewas",
            "ssnit_employee_pesewas",
            "ssnit_employer_pesewas",
            "taxable_pesewas",
            "paye_pesewas",
            "deductions",
            "deductions_pesewas",
            "net_pesewas",
        ]


class PayRunSerializer(serializers.ModelSerializer[PayRun]):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = PayRun
        fields: ClassVar = [
            "id",
            "month",
            "status",
            "status_label",
            "gross_pesewas",
            "paye_pesewas",
            "ssnit_employee_pesewas",
            "ssnit_employer_pesewas",
            "other_deductions_pesewas",
            "net_pesewas",
            "approved_at",
            "paid_at",
        ]


class PrepareSerializer(serializers.Serializer):  # type: ignore[type-arg]
    month = serializers.DateField()


class PayRunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantViewSet):
    serializer_class = PayRunSerializer
    queryset = PayRun.objects.all()
    required_permissions: ClassVar = {
        "list": (MANAGE, APPROVE),
        "retrieve": (MANAGE, APPROVE),
        "prepare": MANAGE,
        "approve": APPROVE,
        "paid": MANAGE,
        "schedule": (MANAGE, APPROVE),
    }

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        run = self.get_object()
        return Response(
            {
                **PayRunSerializer(run).data,
                "payslips": PayslipSerializer(run.payslips.select_related("run"), many=True).data,
            }
        )

    @extend_schema(request=PrepareSerializer, responses=PayRunSerializer)
    @action(detail=False, methods=["post"])
    def prepare(self, request: Request) -> Response:
        data = PrepareSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        run = services.prepare(request=request, month=data.validated_data["month"])
        return Response(PayRunSerializer(run).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=PayRunSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response:
        return Response(
            PayRunSerializer(services.approve(request=request, run=self.get_object())).data
        )

    @extend_schema(request=None, responses=PayRunSerializer)
    @action(detail=True, methods=["post"])
    def paid(self, request: Request, pk: str | None = None) -> Response:
        return Response(
            PayRunSerializer(services.mark_paid(request=request, run=self.get_object())).data
        )

    @extend_schema(
        parameters=[OpenApiParameter("kind", OpenApiTypes.STR, enum=["paye", "ssnit"])],
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"])
    def schedule(self, request: Request, pk: str | None = None) -> HttpResponse:
        run = self.get_object()
        kind = request.query_params.get("kind", "paye")
        if kind not in ("paye", "ssnit"):
            raise ValidationError({"kind": "paye or ssnit"})
        response = HttpResponse(
            services.schedule_csv(run, kind), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = f'attachment; filename="{kind}-{run.month:%Y-%m}.csv"'
        return response


class MyPayslipsView(APIView):
    """Each member of staff's own payslips, once approved."""

    required_permissions: ClassVar = {"GET": SELF}

    @extend_schema(responses=PayslipSerializer(many=True))
    def get(self, request: Request) -> Response:
        slips = (
            Payslip.objects.filter(staff__user_id=request.user.pk)
            .exclude(run__status=PayRun.Status.DRAFT)
            .select_related("run")
            .order_by("-run__month")
        )
        return Response(PayslipSerializer(slips[:36], many=True).data)


class PayslipPdfView(APIView):
    required_permissions: ClassVar = {"GET": (SELF, MANAGE, APPROVE)}

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request: Request, pk: str) -> HttpResponse:
        slip = Payslip.objects.select_related("run", "staff").filter(pk=pk).first()
        if slip is None:
            raise NotFound()
        services.require_own_or_manager(
            request, slip, manage=bool(_perms(request) & {MANAGE, APPROVE})
        )
        response = HttpResponse(services.payslip_pdf(slip), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="payslip-{slip.run.month:%Y-%m}.pdf"'
        )
        return response
