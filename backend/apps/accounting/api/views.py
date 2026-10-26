"""Accounting: the bursar (and proprietor) record spending and other income, set
budgets, and read the reports; the head teacher reads them."""

from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any, ClassVar

from django.db.models import QuerySet
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

from apps.academics.models import AcademicSession
from apps.finance.models import LedgerAccount
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm
from core.views import TenantViewSet

from .. import services
from ..models import Budget, Transaction

VIEW, MANAGE = Perm.ACCOUNTING_VIEW, Perm.ACCOUNTING_MANAGE
READ = (VIEW, MANAGE)


def _dates(request: Request, *, default_days: int = 30) -> tuple[dt.date, dt.date]:
    today = timezone.localdate()
    try:
        end = dt.date.fromisoformat(request.query_params.get("end") or today.isoformat())
        start = dt.date.fromisoformat(
            request.query_params.get("start") or (end - dt.timedelta(days=default_days)).isoformat()
        )
    except ValueError as exc:
        raise ValidationError({"date": "Use YYYY-MM-DD."}) from exc
    if end < start or (end - start).days > 800:
        raise ValidationError({"date": "Choose up to two years, ending after it starts."})
    return start, end


class AccountSerializer(serializers.ModelSerializer[LedgerAccount]):
    class Meta:
        model = LedgerAccount
        fields: ClassVar = ["id", "code", "name", "type"]
        read_only_fields: ClassVar = ["code"]


class AccountsView(APIView):
    """GET: the accounts (``?type=expense|income``). POST {name, type}: a new one."""

    required_permissions: ClassVar = {"GET": READ, "POST": MANAGE}

    @extend_schema(
        parameters=[OpenApiParameter("type", OpenApiTypes.STR)],
        responses=AccountSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        services.ensure_accounts()
        qs = LedgerAccount.objects.order_by("code")
        if kind := request.query_params.get("type"):
            qs = qs.filter(type=kind)
        return Response(AccountSerializer(qs, many=True).data)

    @extend_schema(request=AccountSerializer, responses=AccountSerializer)
    def post(self, request: Request) -> Response:
        data = AccountSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.ensure_accounts()
        account = services.add_account(
            name=data.validated_data["name"], kind=data.validated_data["type"]
        )
        return Response(AccountSerializer(account).data, status=status.HTTP_201_CREATED)


class TransactionSerializer(serializers.ModelSerializer[Transaction]):
    account_name = serializers.CharField(source="account.name", read_only=True)
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    voided = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields: ClassVar = [
            "id",
            "kind",
            "date",
            "account",
            "account_name",
            "amount_pesewas",
            "method",
            "method_label",
            "party",
            "reference",
            "description",
            "voided",
            "void_reason",
            "created_at",
        ]
        read_only_fields: ClassVar = ["void_reason"]

    def get_voided(self, obj: Transaction) -> bool:
        return obj.voided_by_entry_id is not None


class VoidSerializer(serializers.Serializer):  # type: ignore[type-arg]
    reason = serializers.CharField(max_length=200)


class TransactionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, TenantViewSet):
    serializer_class = TransactionSerializer
    required_permissions: ClassVar = {"list": READ, "create": MANAGE, "void": MANAGE}

    def get_queryset(self) -> QuerySet[Transaction]:
        qs = Transaction.objects.select_related("account")
        params = self.request.query_params
        if (kind := params.get("kind")) in Transaction.Kind.values:
            qs = qs.filter(kind=kind)
        if account := params.get("account"):
            qs = qs.filter(account_id=account)
        if params.get("start") or params.get("end"):
            start, end = _dates(self.request)
            qs = qs.filter(date__range=(start, end))
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("kind", OpenApiTypes.STR),
            OpenApiParameter("account", OpenApiTypes.INT),
            OpenApiParameter("start", OpenApiTypes.DATE),
            OpenApiParameter("end", OpenApiTypes.DATE),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(TransactionSerializer(self.get_queryset()[:500], many=True).data)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        data = TransactionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        txn = services.record(
            request=request,
            kind=v["kind"],
            date=v["date"],
            account=v["account"],
            amount=v["amount_pesewas"],
            method=v.get("method", Transaction.Method.CASH),
            party=v["party"],
            reference=v.get("reference", ""),
            description=v.get("description", ""),
        )
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=VoidSerializer, responses=TransactionSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request: Request, pk: str | None = None) -> Response:
        txn = get_object_or_404(Transaction.objects.select_related("entry"), pk=pk)
        data = VoidSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.void(request=request, txn=txn, reason=data.validated_data["reason"])
        return Response(TransactionSerializer(txn).data)


class BudgetSerializer(serializers.Serializer):  # type: ignore[type-arg]
    session = serializers.IntegerField()
    account = serializers.IntegerField()
    amount_pesewas = serializers.IntegerField(min_value=0, max_value=services.MAX_AMOUNT)


class BudgetView(APIView):
    """GET ?session= (default the current year): budget against actual spending.
    PUT {session, account, amount_pesewas}: set one account's budget."""

    required_permissions: ClassVar = {"GET": READ, "PUT": MANAGE}

    def _session(self, value: Any) -> AcademicSession:
        if value:
            return get_object_or_404(AcademicSession, pk=value)
        session = AcademicSession.objects.filter(is_current=True).first()
        if session is None:
            raise NotFound("Set the current academic year first.")
        return session

    @extend_schema(
        parameters=[OpenApiParameter("session", OpenApiTypes.INT)], responses=OpenApiTypes.OBJECT
    )
    def get(self, request: Request) -> Response:
        return Response(
            services.budget_vs_actual(self._session(request.query_params.get("session")))
        )

    @extend_schema(request=BudgetSerializer, responses=OpenApiTypes.OBJECT)
    def put(self, request: Request) -> Response:
        data = BudgetSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        session = self._session(data.validated_data["session"])
        account = get_object_or_404(
            LedgerAccount, pk=data.validated_data["account"], type=LedgerAccount.Type.EXPENSE
        )
        with tenant_atomic():
            Budget.objects.update_or_create(
                account=account,
                session=session,
                defaults={"amount_pesewas": data.validated_data["amount_pesewas"]},
            )
            record_event(
                action="accounting.budget",
                request=request,
                after={
                    "account": account.name,
                    "year": session.name,
                    "amount_pesewas": data.validated_data["amount_pesewas"],
                },
            )
        return Response(services.budget_vs_actual(session))


def _csv(rows: list[list[Any]]) -> str:
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return out.getvalue()


class AccountingReportView(APIView):
    """trial-balance (?end=), income-expenditure (?start=&end=), cash-book (?start=&end=);
    ``?export=csv`` for a spreadsheet."""

    required_permissions: ClassVar = {"GET": READ}

    @extend_schema(
        parameters=[
            OpenApiParameter("start", OpenApiTypes.DATE),
            OpenApiParameter("end", OpenApiTypes.DATE),
            OpenApiParameter("export", OpenApiTypes.STR, enum=["csv"]),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request, kind: str) -> Response | HttpResponse:
        cedi = lambda p: f"{p / 100:.2f}"  # noqa: E731
        if kind == "trial-balance":
            _, end = _dates(request)
            report = services.trial_balance(end)
            rows = [["Code", "Account", "Debit (GHS)", "Credit (GHS)"]] + [
                [r["code"], r["name"], cedi(r["debit_pesewas"]), cedi(r["credit_pesewas"])]
                for r in report["rows"]
            ]
        elif kind == "income-expenditure":
            start, end = _dates(request)
            report = services.income_and_expenditure(start, end)
            rows = [["Income", "", "GHS"]]
            rows += [[r["code"], r["name"], cedi(r["amount_pesewas"])] for r in report["income"]]
            rows += [
                ["", "Total income", cedi(report["income_total_pesewas"])],
                [],
                ["Expenditure", "", "GHS"],
            ]
            rows += [
                [r["code"], r["name"], cedi(r["amount_pesewas"])] for r in report["expenditure"]
            ]
            rows += [
                ["", "Total expenditure", cedi(report["expenditure_total_pesewas"])],
                ["", "Surplus (deficit)", cedi(report["surplus_pesewas"])],
            ]
        elif kind == "cash-book":
            start, end = _dates(request)
            report = services.cash_book(start, end)
            rows = [
                ["Date", "Details", "In (GHS)", "Out (GHS)", "Balance (GHS)"],
                ["", "Opening balance", "", "", cedi(report["opening_pesewas"])],
            ]
            rows += [
                [
                    r["date"],
                    r["memo"],
                    cedi(r["in_pesewas"]),
                    cedi(r["out_pesewas"]),
                    cedi(r["balance_pesewas"]),
                ]
                for r in report["rows"]
            ]
        else:
            raise NotFound("No such report.")
        if request.query_params.get("export") == "csv":
            response = HttpResponse(_csv(rows), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{kind}.csv"'
            return response
        return Response(report)


class AccountingExportView(APIView):
    """The books for outside accounting software (owner's decision: one standard CSV
    that QuickBooks, Xero, Sage and Tally all import, no vendor sync).

    ``journal`` (?start=&end=): one row per journal line, balanced per journal
    number, with Debit and Credit and a signed Amount (debit +, credit -) for
    software that wants one column. ``accounts``: the chart of accounts.
    """

    required_permissions: ClassVar = {"GET": READ}

    @extend_schema(
        parameters=[
            OpenApiParameter("start", OpenApiTypes.DATE),
            OpenApiParameter("end", OpenApiTypes.DATE),
        ],
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    def get(self, request: Request, kind: str) -> HttpResponse:
        from apps.finance.models import JournalLine

        cedi = lambda p: f"{p / 100:.2f}"  # noqa: E731
        if kind == "accounts":
            rows: list[list[Any]] = [["Account code", "Account name", "Account type"]]
            rows += [
                [a.code, a.name, a.get_type_display()]
                for a in LedgerAccount.objects.order_by("code")
            ]
            name = "chart-of-accounts.csv"
        elif kind == "journal":
            start, end = _dates(request, default_days=31)
            lines = (
                JournalLine.objects.filter(
                    entry__posted_at__date__gte=start, entry__posted_at__date__lte=end
                )
                .select_related("entry", "account")
                .order_by("entry__posted_at", "entry_id", "pk")
            )
            rows = [
                [
                    "Journal number",
                    "Date",
                    "Account code",
                    "Account name",
                    "Account type",
                    "Debit",
                    "Credit",
                    "Amount",
                    "Description",
                    "Source",
                    "Currency",
                ]
            ]
            numbers: dict[Any, int] = {}
            for line in lines:
                number = numbers.setdefault(line.entry_id, len(numbers) + 1)
                rows.append(
                    [
                        f"NX{start:%Y%m}-{number:05d}",
                        timezone.localtime(line.entry.posted_at).date().isoformat(),
                        line.account.code,
                        line.account.name,
                        line.account.get_type_display(),
                        cedi(line.debit_pesewas) if line.debit_pesewas else "",
                        cedi(line.credit_pesewas) if line.credit_pesewas else "",
                        cedi(line.debit_pesewas - line.credit_pesewas),
                        line.entry.memo,
                        line.entry.source_type,
                        "GHS",
                    ]
                )
            name = f"journal-{start}-to-{end}.csv"
        else:
            raise NotFound("No such export.")
        with tenant_atomic():
            record_event(
                action="accounting.exported",
                request=request,
                after={"kind": kind, "rows": len(rows) - 1},
            )
        response = HttpResponse(_csv(rows), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
