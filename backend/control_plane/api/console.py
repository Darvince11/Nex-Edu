"""Super Admin console: pricing and billing, audit logs, announcements, system.

Every view is platform-only (``IsPlatformStaff``). Reading and changing can
need different platform roles; ``ConsoleView.platform_roles`` picks by method.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from control_plane import announcements, audit_log, billing, problems, security
from control_plane.audit import record_platform_event, verify_platform_chain
from control_plane.models import (
    BillingSettings,
    GhanaRegion,
    PlatformAnnouncement,
    PlatformAnnouncementRecipient,
    PlatformRole,
    PriceBandSetting,
    Problem,
    SubscriptionPayment,
    Tenant,
    VulnerabilityScan,
)
from core.permissions import IsPlatformStaff
from core.tasks import enqueue_after_commit

SUPER = (PlatformRole.SUPER_ADMIN,)
SUPPORT = (PlatformRole.SUPER_ADMIN, PlatformRole.SUPPORT)
MONEY = (PlatformRole.SUPER_ADMIN, PlatformRole.BILLING)
EVERYONE = tuple(PlatformRole.values)


class ConsoleView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformStaff]
    tenant_scoped = False
    read_roles: tuple[str, ...] = SUPPORT
    write_roles: tuple[str, ...] = SUPER

    @property
    def platform_roles(self) -> tuple[str, ...]:
        return self.read_roles if self.request.method in SAFE_METHODS else self.write_roles


# --- Pricing and billing -----------------------------------------------------------------


class BillingPeriodSerializer(serializers.Serializer[Any]):
    period = serializers.ChoiceField(choices=BillingSettings.Period.choices)


class PricingView(ConsoleView):
    """Price bands, the billing period, and which band each school is in.
    PATCH sets the billing period (super admin)."""

    read_roles = MONEY
    write_roles = SUPER

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(billing.pricing_overview())

    @extend_schema(request=BillingPeriodSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request: Request) -> Response:
        data = BillingPeriodSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        billing.set_period(request=request, period=data.validated_data["period"])
        return Response(billing.pricing_overview())


class BandPriceSerializer(serializers.Serializer[Any]):
    price_pesewas = serializers.IntegerField(min_value=100, max_value=100_000_000)
    reason = serializers.CharField(max_length=300)


class PriceBandView(ConsoleView):
    """Change one band's price. Super admin only; the reason is kept in the audit log."""

    read_roles = SUPER
    write_roles = SUPER

    @extend_schema(request=BandPriceSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, code: str) -> Response:
        get_object_or_404(PriceBandSetting, code=code)
        data = BandPriceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        billing.update_band(request=request, code=code, **data.validated_data)
        return Response(billing.pricing_overview())


class SubscriptionPaymentSerializer(serializers.ModelSerializer[SubscriptionPayment]):
    school = serializers.SlugRelatedField(
        source="tenant", slug_field="slug", queryset=Tenant.objects.all()
    )

    class Meta:
        model = SubscriptionPayment
        fields: ClassVar = [
            "school",
            "amount_pesewas",
            "period_label",
            "method",
            "reference",
            "received_on",
            "note",
        ]


class BillingHistoryView(ConsoleView):
    """Subscription payments received from schools. ?school= and ?before_month=1
    (only payments before the current month). POST records a payment."""

    read_roles = MONEY
    write_roles = MONEY

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(
            billing.history(
                school=request.query_params.get("school") or None,
                before_month=request.query_params.get("before_month") == "1",
            )
        )

    @extend_schema(request=SubscriptionPaymentSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = SubscriptionPaymentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        fields = dict(data.validated_data)
        tenant = fields.pop("tenant")
        payment = billing.record_payment(request=request, tenant=tenant, **fields)
        return Response({"id": payment.pk}, status=status.HTTP_201_CREATED)


# --- Audit logs --------------------------------------------------------------------------


class AuditLogView(ConsoleView):
    """Every Nex Edu event, filed by school. ?school=<slug>|platform, ?action=, ?actor=,
    ?days=, ?before=<seq> for the next page."""

    read_roles = SUPPORT

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        before = request.query_params.get("before", "")
        return Response(
            audit_log.rows(
                audit_log.filtered(request.query_params),
                before=int(before) if before.isdigit() else None,
            )
        )


class AuditGroupsView(ConsoleView):
    """How many events each school (and the platform itself) had in the last 30 days."""

    read_roles = SUPPORT

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(audit_log.school_groups())


class MyAuditLogView(ConsoleView):
    """The signed-in staff member's own actions and sign-ins."""

    read_roles = EVERYONE

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        events = audit_log.filtered(request.query_params).filter(actor_id=request.user.pk)
        before = request.query_params.get("before", "")
        return Response(audit_log.rows(events, before=int(before) if before.isdigit() else None))


class AuditIntegrityView(ConsoleView):
    """Re-checks the hash chain: has any past entry been changed or removed?"""

    read_roles = SUPPORT

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        result = verify_platform_chain()
        return Response(
            {
                "valid": result.valid,
                "checked": result.checked,
                "first_bad_seq": result.first_bad_seq,
                "reason": result.reason,
            }
        )


# --- Announcements to proprietors --------------------------------------------------------


class PlatformAnnouncementSerializer(serializers.ModelSerializer[PlatformAnnouncement]):
    read_count = serializers.SerializerMethodField()
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    region = serializers.ChoiceField(choices=GhanaRegion.choices, required=False, allow_blank=True)

    class Meta:
        model = PlatformAnnouncement
        fields: ClassVar = [
            "id",
            "title",
            "body",
            "audience",
            "band_code",
            "region",
            "email",
            "status",
            "recipient_count",
            "read_count",
            "created_by_email",
            "created_at",
            "published_at",
        ]
        read_only_fields: ClassVar = [
            "status",
            "recipient_count",
            "read_count",
            "created_by_email",
            "created_at",
            "published_at",
        ]

    def get_read_count(self, obj: PlatformAnnouncement) -> int:
        return obj.recipients.filter(read_at__isnull=False).count()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        announcements.validate({**(self.instance.__dict__ if self.instance else {}), **attrs})
        return attrs


class AnnouncementListView(ConsoleView):
    read_roles = SUPPORT
    write_roles = SUPER

    @extend_schema(responses=PlatformAnnouncementSerializer(many=True))
    def get(self, request: Request) -> Response:
        items = PlatformAnnouncement.objects.select_related("created_by")[:100]
        return Response(PlatformAnnouncementSerializer(items, many=True).data)

    @extend_schema(request=PlatformAnnouncementSerializer, responses=PlatformAnnouncementSerializer)
    def post(self, request: Request) -> Response:
        data = PlatformAnnouncementSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        item = data.save(created_by=request.user)
        record_platform_event(
            action="announcement.drafted", request=request, target=item, data={"title": item.title}
        )
        return Response(PlatformAnnouncementSerializer(item).data, status=status.HTTP_201_CREATED)


class AnnouncementDetailView(ConsoleView):
    """Drafts can be edited or deleted; sent announcements are kept as they were."""

    read_roles = SUPPORT
    write_roles = SUPER

    def _get(self, pk: str) -> PlatformAnnouncement:
        return get_object_or_404(PlatformAnnouncement, pk=pk)

    @extend_schema(request=PlatformAnnouncementSerializer, responses=PlatformAnnouncementSerializer)
    def patch(self, request: Request, pk: str) -> Response:
        item = self._get(pk)
        if item.status != PlatformAnnouncement.Status.DRAFT:
            return Response({"detail": "Sent announcements can't be changed."}, status=400)
        data = PlatformAnnouncementSerializer(item, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        return Response(PlatformAnnouncementSerializer(data.save()).data)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, pk: str) -> Response:
        item = self._get(pk)
        if item.status != PlatformAnnouncement.Status.DRAFT:
            return Response({"detail": "Sent announcements can't be deleted."}, status=400)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AnnouncementPublishView(ConsoleView):
    write_roles = SUPER

    @extend_schema(request=None, responses=PlatformAnnouncementSerializer)
    def post(self, request: Request, pk: str) -> Response:
        item = get_object_or_404(PlatformAnnouncement, pk=pk)
        announcements.publish(request=request, announcement=item)
        return Response(PlatformAnnouncementSerializer(item).data)


class FromNexEduView(APIView):
    """For proprietors: Nex Edu announcements they haven't dismissed yet."""

    permission_classes = [IsAuthenticated]
    tenant_scoped = False

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(
            [
                {
                    "id": r.announcement.pk,
                    "title": r.announcement.title,
                    "body": r.announcement.body,
                    "published_at": r.announcement.published_at,
                }
                for r in announcements.for_user(request.user)
            ]
        )


class FromNexEduReadView(APIView):
    permission_classes = [IsAuthenticated]
    tenant_scoped = False

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request, pk: str) -> Response:
        PlatformAnnouncementRecipient.objects.filter(
            announcement_id=pk, user=request.user, read_at__isnull=True
        ).update(read_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- System: problems, sign-in activity, updates, vulnerabilities ------------------------


class ProblemSerializer(serializers.ModelSerializer[Problem]):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Problem
        fields: ClassVar = [
            "id",
            "kind",
            "kind_label",
            "severity",
            "title",
            "location",
            "detail",
            "last_path",
            "schools",
            "count",
            "first_seen",
            "last_seen",
            "status",
            "note",
            "updated_by_email",
        ]
        read_only_fields: ClassVar = [f for f in fields if f not in ("status", "note")]


class ProblemListView(ConsoleView):
    """?status=open (new + investigating, the default), fixed, ignored or all; ?kind=."""

    read_roles = SUPPORT

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        items = Problem.objects.all()
        wanted = request.query_params.get("status", "open")
        if wanted == "open":
            items = items.filter(status__in=[Problem.Status.NEW, Problem.Status.INVESTIGATING])
        elif wanted in Problem.Status.values:
            items = items.filter(status=wanted)
        if (kind := request.query_params.get("kind")) in Problem.Kind.values:
            items = items.filter(kind=kind)
        open_items = Problem.objects.filter(
            status__in=[Problem.Status.NEW, Problem.Status.INVESTIGATING]
        )
        return Response(
            {
                "open": open_items.count(),
                "critical_open": open_items.filter(severity=Problem.Severity.CRITICAL).count(),
                "last_24h": Problem.objects.filter(
                    last_seen__gte=timezone.now() - timezone.timedelta(hours=24)
                ).count(),
                "problems": ProblemSerializer(
                    items.order_by("-severity", "-last_seen")[:200], many=True
                ).data,
            }
        )


class ProblemDetailView(ConsoleView):
    read_roles = SUPPORT
    write_roles = SUPPORT

    @extend_schema(request=ProblemSerializer, responses=ProblemSerializer)
    def patch(self, request: Request, pk: int) -> Response:
        problem = get_object_or_404(Problem, pk=pk)
        data = ProblemSerializer(problem, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        before = problem.status
        problem = data.save(updated_by_email=request.user.email)
        if before != problem.status:
            record_platform_event(
                action="problem.status_changed",
                request=request,
                target=problem,
                data={"title": problem.title[:120], "before": before, "after": problem.status},
            )
        return Response(ProblemSerializer(problem).data)


class SecurityActivityView(ConsoleView):
    """Failed sign-ins, suspicious addresses, password resets and authenticator changes."""

    read_roles = SUPPORT

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        hours = request.query_params.get("hours", "24")
        hours_n = int(hours) if hours.isdigit() and 1 <= int(hours) <= 24 * 30 else 24
        return Response(security.sign_in_activity(hours_n))


class SystemStatusView(ConsoleView):
    """Versions, school databases needing an update, security checks, the latest
    vulnerability scan and health checks. POST runs the health checks now."""

    read_roles = SUPPORT
    write_roles = SUPPORT

    def _payload(self) -> dict[str, Any]:
        scan = VulnerabilityScan.objects.first()
        return {
            **security.system_status(),
            "scan": {
                "started_at": scan.started_at,
                "finished_at": scan.finished_at,
                "packages_checked": scan.packages_checked,
                "findings": scan.findings,
                "error": scan.error,
            }
            if scan
            else None,
        }

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(self._payload())

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        results = problems.run_health_checks()
        return Response({**self._payload(), "health": results})


class VulnerabilityScanView(ConsoleView):
    """Start a scan now (it runs in the background; the page checks back)."""

    write_roles = SUPER

    @extend_schema(request=None, responses={202: None})
    def post(self, request: Request) -> Response:
        from control_plane.tasks import vulnerability_scan

        record_platform_event(action="system.vulnerability_scan_started", request=request)
        enqueue_after_commit(vulnerability_scan)
        return Response(status=status.HTTP_202_ACCEPTED)


class BrowserErrorSerializer(serializers.Serializer[Any]):
    message = serializers.CharField(max_length=500)
    source = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    stack = serializers.CharField(max_length=6000, required=False, allow_blank=True, default="")
    page = serializers.CharField(max_length=300)
    school = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")


class BrowserErrorThrottle(UserRateThrottle):
    # Its own counter: sharing the default "user" scope would block reports from
    # anyone who has simply been busy in the app.
    scope = "browser-errors"
    rate = "30/hour"


class BrowserErrorView(APIView):
    """Signed-in people's browsers report screen errors here (scrubbed on arrival)."""

    permission_classes = [IsAuthenticated]
    tenant_scoped = False
    throttle_classes = [BrowserErrorThrottle]

    @extend_schema(request=BrowserErrorSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        data = BrowserErrorSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        problems.report_browser_error(**data.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Modules ---------------------------------------------------------------------------


class TenantModuleSerializer(serializers.Serializer[Any]):
    code = serializers.CharField(max_length=30)
    action = serializers.ChoiceField(choices=["grant", "revoke", "activate", "deactivate"])
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    confirm = serializers.BooleanField(required=False, default=False)


class TenantModulesView(ConsoleView):
    """A school's modules as Nex Edu sees them. Super admins grant or remove paid
    add-ons and can switch a module on or off for the school (always logged)."""

    read_roles = SUPPORT
    write_roles = SUPER

    def _payload(self, tenant: Tenant) -> dict[str, Any]:
        from control_plane import modules

        return {"modules": modules.catalogue(tenant), "history": modules.history(tenant)}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, slug: str) -> Response:
        return Response(self._payload(get_object_or_404(Tenant, slug=slug)))

    @extend_schema(request=TenantModuleSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, slug: str) -> Response:
        from control_plane import modules

        tenant = get_object_or_404(Tenant, slug=slug, status=Tenant.Status.ACTIVE)
        data = TenantModuleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if v["action"] in ("grant", "revoke"):
            modules.set_granted(
                tenant=tenant,
                code=v["code"],
                granted=v["action"] == "grant",
                request=request,
                reason=v["reason"],
            )
        else:
            if not v["reason"].strip():
                return Response(
                    {"reason": ["Say why Nex Edu is changing this for the school."]}, status=400
                )
            modules.set_active(
                tenant=tenant,
                code=v["code"],
                active=v["action"] == "activate",
                request=request,
                confirm=v["confirm"],
                by_platform=True,
                reason=v["reason"],
            )
        return Response(self._payload(tenant))


class ModulePriceSerializer(serializers.Serializer[Any]):
    price_pesewas = serializers.IntegerField(min_value=0, max_value=100_000_000)
    reason = serializers.CharField(max_length=300)


class ModulePricesView(ConsoleView):
    """Optional modules and their prices. GH₵0 means included in every band."""

    read_roles = MONEY
    write_roles = SUPER

    def _payload(self) -> list[dict[str, Any]]:
        from control_plane.modules import prices
        from core.modules import MODULES

        cost = prices()
        return [
            {
                "code": m.code,
                "name": m.name,
                "description": m.description,
                "available": m.available,
                "price_pesewas": cost.get(m.code, 0),
            }
            for m in MODULES
            if not m.core
        ]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(self._payload())


class ModulePriceView(ConsoleView):
    read_roles = SUPER
    write_roles = SUPER

    @extend_schema(request=ModulePriceSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, code: str) -> Response:
        from control_plane.modules import set_price

        data = ModulePriceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        set_price(code=code, request=request, **data.validated_data)
        return Response(ModulePricesView()._payload())
