"""Phase 7 APIs: school lifecycle, subscription invoices, SMS bundles, support
access and operations (Super Admin console), and the proprietor's own billing,
export and support-access pages.

The proprietor's pages need no school selected (``tenant_scoped = False``): a
suspended school is closed to everyone, but its proprietor must still be able to
pay, and a closed school's proprietor to download its export.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.files.storage import default_storage
from django.db.models import Count, Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from control_plane import jobs, lifecycle, subscriptions, support_access
from control_plane.api.console import MONEY, SUPER, SUPPORT, ConsoleView
from control_plane.audit import record_platform_event
from control_plane.models import (
    BillingSettings,
    Cell,
    Membership,
    Role,
    SmsBundle,
    SubscriptionCharge,
    SubscriptionInvoice,
    SubscriptionPayment,
    SupportGrant,
    Tenant,
    TenantMigrationRun,
)
from integrations.payments import PaymentProviderError

# --- Super Admin: lifecycle ---------------------------------------------------------------


class LifecycleSerializer(serializers.Serializer[Any]):
    action = serializers.ChoiceField(choices=["suspend", "reactivate", "offboard"])
    reason = serializers.CharField(max_length=300, allow_blank=True, default="")
    confirm = serializers.CharField(
        max_length=40,
        allow_blank=True,
        default="",
        help_text="The school's web address, to close it",
    )


def _state(tenant: Tenant) -> dict[str, Any]:
    return {
        "status": tenant.status,
        "status_reason": tenant.status_reason,
        "status_note": tenant.status_note,
        "status_changed_at": tenant.status_changed_at,
        "purge_after": tenant.purge_after,
        "purged_at": tenant.purged_at,
    }


class TenantLifecycleView(ConsoleView):
    """Suspend, reactivate or close a school (Super Admin). Closing exports the
    school's data for the proprietor and destroys it after 90 days."""

    read_roles = SUPPORT
    write_roles = SUPER

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, slug: str) -> Response:
        return Response(_state(get_object_or_404(Tenant, slug=slug)))

    @extend_schema(request=LifecycleSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, slug: str) -> Response:
        tenant = get_object_or_404(Tenant, slug=slug)
        data = LifecycleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        action, reason = data.validated_data["action"], data.validated_data["reason"]
        if action == "suspend":
            tenant = lifecycle.suspend(
                tenant, reason=lifecycle.Reason.PLATFORM, note=reason, request=request
            )
        elif action == "reactivate":
            tenant = lifecycle.reactivate(tenant, note=reason, request=request)
        else:
            if data.validated_data["confirm"] != tenant.slug:
                raise ValidationError({"confirm": "Type the school's web address to close it."})
            tenant = lifecycle.offboard(tenant, note=reason, request=request)
        return Response(_state(tenant))


# --- Super Admin: invoices, billing settings, SMS -----------------------------------------


def _invoice(i: SubscriptionInvoice) -> dict[str, Any]:
    today = timezone.localdate()
    return {
        "id": str(i.pk),
        "number": i.number,
        "school": i.tenant.name,
        "slug": i.tenant.slug,
        "month": i.month,
        "lines": i.lines,
        "total_pesewas": i.total_pesewas,
        "issued_on": i.issued_on,
        "due_on": i.due_on,
        "status": i.status,
        "status_label": i.get_status_display(),
        "overdue_days": max((today - i.due_on).days, 0)
        if i.status == SubscriptionInvoice.Status.OPEN
        else 0,
        "paid_on": i.paid_on,
        "void_reason": i.void_reason,
    }


class InvoiceListView(ConsoleView):
    """Every school's invoices (?status=open|paid|void, ?school=). POST makes this
    month's invoices now for schools that lack one."""

    read_roles = MONEY
    write_roles = MONEY

    @extend_schema(
        parameters=[OpenApiParameter("status", str), OpenApiParameter("school", str)],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request) -> Response:
        rows = SubscriptionInvoice.objects.select_related("tenant")
        if value := request.query_params.get("status"):
            rows = rows.filter(status=value)
        if value := request.query_params.get("school"):
            rows = rows.filter(tenant__slug=value)
        open_rows = SubscriptionInvoice.objects.filter(status=SubscriptionInvoice.Status.OPEN)
        today = timezone.localdate()
        return Response(
            {
                "open_pesewas": sum(i.total_pesewas for i in open_rows),
                "overdue": open_rows.filter(due_on__lt=today).count(),
                "invoices": [_invoice(i) for i in rows[:500]],
            }
        )

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        made = subscriptions.issue_month()
        record_platform_event(action="billing.invoices_run", request=request, data={"made": made})
        return Response({"made": made}, status=status.HTTP_201_CREATED)


class InvoiceActionSerializer(serializers.Serializer[Any]):
    action = serializers.ChoiceField(choices=["mark_paid", "void"])
    method = serializers.ChoiceField(
        choices=[c for c in SubscriptionPayment.Method.values if c != "paystack"], required=False
    )
    reference = serializers.CharField(max_length=80, allow_blank=True, default="")
    received_on = serializers.DateField(required=False)
    reason = serializers.CharField(max_length=300, allow_blank=True, default="")


class InvoiceDetailView(ConsoleView):
    """Record a payment made outside Paystack (bank, cash...), or cancel an invoice."""

    read_roles = MONEY
    write_roles = MONEY

    @extend_schema(
        operation_id="platform_invoice_action",
        request=InvoiceActionSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request: Request, pk: str) -> Response:
        invoice = get_object_or_404(SubscriptionInvoice.objects.select_related("tenant"), pk=pk)
        data = InvoiceActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if v["action"] == "void":
            invoice = subscriptions.void(invoice, reason=v["reason"], request=request)
        else:
            if not v.get("method"):
                raise ValidationError({"method": "How was it paid?"})
            on = v.get("received_on") or timezone.localdate()
            if on > timezone.localdate():
                raise ValidationError({"received_on": "A payment can't be received in the future."})
            subscriptions.mark_paid(
                invoice,
                method=v["method"],
                reference=v["reference"],
                request=request,
                recorded_by=request.user,
                received_on=on,
            )
            invoice.refresh_from_db()
        return Response(_invoice(invoice))


class BillingRulesSerializer(serializers.ModelSerializer[BillingSettings]):
    class Meta:
        model = BillingSettings
        fields = ["due_days", "sms_included_monthly"]
        extra_kwargs = {
            "due_days": {"min_value": 1, "max_value": 60},
            "sms_included_monthly": {"min_value": 0, "max_value": 1_000_000},
        }


class BillingRulesView(ConsoleView):
    """Days to pay an invoice, and the SMS every school gets each month."""

    read_roles = MONEY
    write_roles = SUPER

    @extend_schema(responses=BillingRulesSerializer)
    def get(self, request: Request) -> Response:
        return Response(BillingRulesSerializer(BillingSettings.load()).data)

    @extend_schema(request=BillingRulesSerializer, responses=BillingRulesSerializer)
    def patch(self, request: Request) -> Response:
        rules = BillingSettings.load()
        before = BillingRulesSerializer(rules).data
        data = BillingRulesSerializer(rules, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        record_platform_event(
            action="billing.rules_changed",
            request=request,
            target=rules,
            data={"before": before, "after": data.data},
        )
        return Response(data.data)


class SmsBundleSerializer(serializers.ModelSerializer[SmsBundle]):
    class Meta:
        model = SmsBundle
        fields = ["code", "label", "sms", "price_pesewas", "is_active", "position"]
        extra_kwargs = {
            "sms": {"min_value": 1, "max_value": 1_000_000},
            "price_pesewas": {"min_value": 1, "max_value": 100_000_000},
        }


class SmsBundleListView(ConsoleView):
    """The SMS bundles schools can buy."""

    read_roles = MONEY
    write_roles = SUPER

    @extend_schema(responses=SmsBundleSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(SmsBundleSerializer(SmsBundle.objects.all(), many=True).data)

    @extend_schema(request=SmsBundleSerializer, responses=SmsBundleSerializer)
    def post(self, request: Request) -> Response:
        data = SmsBundleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        bundle = data.save()
        record_platform_event(
            action="billing.sms_bundle_added", request=request, target=bundle, data=data.data
        )
        return Response(data.data, status=status.HTTP_201_CREATED)


class SmsBundleDetailView(ConsoleView):
    read_roles = MONEY
    write_roles = SUPER

    @extend_schema(request=SmsBundleSerializer, responses=SmsBundleSerializer)
    def patch(self, request: Request, code: str) -> Response:
        bundle = get_object_or_404(SmsBundle, code=code)
        before = SmsBundleSerializer(bundle).data
        data = SmsBundleSerializer(bundle, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        record_platform_event(
            action="billing.sms_bundle_changed",
            request=request,
            target=bundle,
            data={"before": before, "after": data.data},
        )
        return Response(data.data)


class SmsGiftSerializer(serializers.Serializer[Any]):
    sms = serializers.IntegerField(min_value=1, max_value=100_000)
    reason = serializers.CharField(max_length=300)


class TenantSmsView(ConsoleView):
    """A school's SMS: the allowance, bought SMS left; POST adds SMS free of charge."""

    read_roles = MONEY
    write_roles = SUPER

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, slug: str) -> Response:
        return Response(subscriptions.sms_allowance(get_object_or_404(Tenant, slug=slug)))

    @extend_schema(request=SmsGiftSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, slug: str) -> Response:
        tenant = get_object_or_404(Tenant, slug=slug)
        data = SmsGiftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        subscriptions.add_sms(tenant, data.validated_data["sms"])
        record_platform_event(
            action="billing.sms_added",
            request=request,
            tenant=tenant,
            data={"sms": data.validated_data["sms"]},
            reason=data.validated_data["reason"],
        )
        return Response(subscriptions.sms_allowance(tenant))


# --- Super Admin: support access and operations -------------------------------------------


class TenantSupportView(ConsoleView):
    """The school's set-up (never pupils), while its proprietor allows support access."""

    read_roles = SUPPORT
    write_roles = SUPPORT

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, slug: str) -> Response:
        tenant = get_object_or_404(Tenant, slug=slug)
        grant = support_access.active_grant(tenant)
        if request.query_params.get("look") != "1":
            return Response(
                {
                    "open": grant is not None,
                    "expires_at": grant.expires_at if grant else None,
                    "reason": grant.reason if grant else "",
                }
            )
        return Response(support_access.configuration(request=request, tenant=tenant))


class OperationsView(ConsoleView):
    """Scheduled jobs, server groups (cells) and school database migrations."""

    read_roles = SUPPORT

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        live = ~Q(tenants__status=Tenant.Status.OFFBOARDED)
        cells = Cell.objects.annotate(used=Count("tenants", filter=live)).order_by("name")
        failed = TenantMigrationRun.objects.filter(succeeded=False).select_related("tenant")
        return Response(
            {
                "jobs": jobs.overview(),
                "cells": [
                    {
                        "name": c.name,
                        "region": c.region,
                        "schools": c.used,
                        "capacity": c.capacity,
                        "accepting": c.is_accepting,
                    }
                    for c in cells
                ],
                "migrations": [
                    {
                        "school": r.tenant.name,
                        "slug": r.tenant.slug,
                        "started_at": r.started_at,
                        "finished_at": r.finished_at,
                        "succeeded": r.succeeded,
                        "schema_version": r.schema_version,
                        "error": r.error[:500],
                    }
                    for r in TenantMigrationRun.objects.select_related("tenant")[:50]
                ],
                "migration_failures_7d": failed.filter(
                    started_at__gte=timezone.now() - dt.timedelta(days=7)
                ).count(),
                "lifecycle": {
                    "suspended": Tenant.objects.filter(status=Tenant.Status.SUSPENDED).count(),
                    "closing": Tenant.objects.filter(
                        status=Tenant.Status.OFFBOARDED, purged_at__isnull=True
                    ).count(),
                },
            }
        )


# --- The proprietor's own pages -----------------------------------------------------------


def _owned(request: Request, slug: str) -> Tenant:
    tenant = get_object_or_404(Tenant, slug=slug)
    if not Membership.objects.filter(
        user=request.user, tenant=tenant, role=Role.OWNER, is_active=True
    ).exists():
        raise PermissionDenied("Only the school's proprietor can do this.")
    if tenant.purged_at:
        raise PermissionDenied("This school's data has been destroyed.")
    return tenant


class OwnerView(APIView):
    permission_classes = [IsAuthenticated]
    tenant_scoped = False


class AccountBillingView(OwnerView):
    """The proprietor's invoices, SMS and bundles; works while suspended or closed."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, slug: str) -> Response:
        return Response(subscriptions.account(_owned(request, slug)))


class SubscriptionPaySerializer(serializers.Serializer[Any]):
    invoice = serializers.UUIDField(required=False)
    bundle = serializers.SlugField(required=False)


class AccountPayView(OwnerView):
    """Start a Paystack payment (mobile money or card) for an invoice or an SMS bundle."""

    @extend_schema(request=SubscriptionPaySerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, slug: str) -> Response:
        tenant = _owned(request, slug)
        data = SubscriptionPaySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        invoice = bundle = None
        if pk := data.validated_data.get("invoice"):
            invoice = get_object_or_404(SubscriptionInvoice, pk=pk, tenant=tenant)
        if code := data.validated_data.get("bundle"):
            bundle = get_object_or_404(SmsBundle, code=code)
        try:
            charge = subscriptions.start_checkout(
                request=request, tenant=tenant, invoice=invoice, bundle=bundle
            )
        except PaymentProviderError:
            return Response(
                {"detail": "Paystack isn't answering. Try again in a few minutes."}, status=502
            )
        return Response(
            {"reference": charge.reference, "authorization_url": charge.authorization_url},
            status=status.HTTP_201_CREATED,
        )


class AccountChargeView(OwnerView):
    """After Paystack sends the proprietor back: check the payment now."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, slug: str, reference: str) -> Response:
        tenant = _owned(request, slug)
        charge = get_object_or_404(SubscriptionCharge, reference=reference, tenant=tenant)
        try:
            charge = subscriptions.verify_charge(charge)
        except PaymentProviderError:
            pass  # the webhook or the reconciliation job will finish it
        return Response({"reference": charge.reference, "status": charge.status})


class AccountExportView(OwnerView):
    """The closing export: everything the school kept. Proprietor only (Nex Edu
    staff never download it, since it holds pupils' records)."""

    @extend_schema(responses={(200, "application/zip"): OpenApiTypes.BINARY})
    def get(self, request: Request, slug: str) -> Any:
        tenant = _owned(request, slug)
        if not tenant.export_key:
            raise ValidationError({"detail": "There is no export for this school."})
        record_platform_event(action="tenant.export_downloaded", request=request, tenant=tenant)
        name = f"{tenant.slug}-nexedu-export.zip"
        if getattr(default_storage, "querystring_auth", False):
            url = default_storage.url(
                tenant.export_key,
                parameters={"ResponseContentDisposition": f'attachment; filename="{name}"'},
            )
            return JsonResponse({"url": url})
        response = FileResponse(
            default_storage.open(tenant.export_key, "rb"), content_type="application/zip"
        )
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response


class GrantSerializer(serializers.Serializer[Any]):
    hours = serializers.IntegerField(min_value=1, max_value=support_access.MAX_HOURS)
    reason = serializers.CharField(max_length=300)


class AccountSupportView(OwnerView):
    """The proprietor lets Nex Edu support see the school's set-up for a while."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, slug: str) -> Response:
        return Response({"grants": support_access.history(_owned(request, slug))})

    @extend_schema(request=GrantSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, slug: str) -> Response:
        tenant = _owned(request, slug)
        if tenant.status != Tenant.Status.ACTIVE:
            raise ValidationError({"detail": "Only an active school can give support access."})
        data = GrantSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        support_access.grant(request=request, tenant=tenant, **data.validated_data)
        return Response({"grants": support_access.history(tenant)}, status=status.HTTP_201_CREATED)


class AccountSupportRevokeView(OwnerView):
    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, slug: str, pk: str) -> Response:
        tenant = _owned(request, slug)
        item = get_object_or_404(SupportGrant, pk=pk, tenant=tenant)
        support_access.revoke(request=request, item=item)
        return Response({"grants": support_access.history(tenant)})
