"""Developer API: the proprietor's keys and webhooks (in the school), and the
read-only API other systems call with a key.

Key calls carry ``Authorization: Bearer nxk_...``; the key picks the school, so no
school header is needed. Each scope opens one kind of record, read-only, and
nothing about guardians' contacts, health or money beyond fees is exposed.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from control_plane import developer
from control_plane.audit import record_platform_event
from control_plane.models import ApiKey, WebhookEndpoint
from control_plane.tenancy import require_tenant, tenant_context
from core.rbac import Perm

MANAGE = Perm.INTEGRATIONS_MANAGE

# --- The proprietor's settings (inside the school) ----------------------------------------


class KeyCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=80)
    scopes = serializers.ListField(child=serializers.ChoiceField(choices=list(developer.SCOPES)))


def _key(k: ApiKey) -> dict[str, Any]:
    return {
        "id": str(k.pk),
        "name": k.name,
        "prefix": k.prefix,
        "scopes": k.scopes,
        "created_at": k.created_at,
        "last_used_at": k.last_used_at,
        "revoked_at": k.revoked_at,
    }


class IntegrationsView(APIView):
    """What keys can read and which events webhooks can send."""

    module = developer.MODULE
    required_permissions: ClassVar = {"GET": MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(
            {
                "scopes": [{"code": c, "label": label} for c, label in developer.SCOPES.items()],
                "events": [{"code": c, "label": label} for c, label in developer.EVENTS.items()],
            }
        )


class ApiKeyListView(APIView):
    module = developer.MODULE
    required_permissions: ClassVar = {"GET": MANAGE, "POST": MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response([_key(k) for k in ApiKey.objects.filter(tenant=require_tenant())])

    @extend_schema(request=KeyCreateSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = KeyCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        key, raw = developer.create_key(
            tenant=require_tenant(), user=request.user, **data.validated_data
        )
        record_platform_event(
            action="developer.key_created",
            request=request,
            tenant=require_tenant(),
            target=key,
            data={"name": key.name, "scopes": key.scopes},
        )
        return Response({**_key(key), "key": raw}, status=status.HTTP_201_CREATED)


class ApiKeyRevokeView(APIView):
    module = developer.MODULE
    required_permissions: ClassVar = {"POST": MANAGE}

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, pk: str) -> Response:
        key = get_object_or_404(ApiKey, pk=pk, tenant=require_tenant())
        if key.revoked_at is None:
            key.revoked_at = timezone.now()
            key.save(update_fields=["revoked_at"])
            record_platform_event(
                action="developer.key_revoked", request=request, tenant=key.tenant, target=key
            )
        return Response(_key(key))


class WebhookCreateSerializer(serializers.Serializer[Any]):
    url = serializers.URLField(max_length=500)
    events = serializers.ListField(child=serializers.ChoiceField(choices=list(developer.EVENTS)))


def _hook(e: WebhookEndpoint) -> dict[str, Any]:
    last = e.deliveries.first()
    return {
        "id": str(e.pk),
        "url": e.url,
        "events": e.events,
        "is_active": e.is_active,
        "created_at": e.created_at,
        "last_delivery": {"status": last.status, "at": last.created_at, "error": last.error}
        if last
        else None,
    }


class WebhookListView(APIView):
    module = developer.MODULE
    required_permissions: ClassVar = {"GET": MANAGE, "POST": MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response([_hook(e) for e in WebhookEndpoint.objects.filter(tenant=require_tenant())])

    @extend_schema(request=WebhookCreateSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = WebhookCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        endpoint, secret = developer.create_webhook(
            tenant=require_tenant(), user=request.user, **data.validated_data
        )
        record_platform_event(
            action="developer.webhook_added",
            request=request,
            tenant=require_tenant(),
            target=endpoint,
            data={"url": endpoint.url, "events": endpoint.events},
        )
        return Response({**_hook(endpoint), "secret": secret}, status=status.HTTP_201_CREATED)


class WebhookDetailView(APIView):
    """GET: recent deliveries. DELETE: stop sending to this address."""

    module = developer.MODULE
    required_permissions: ClassVar = {"GET": MANAGE, "DELETE": MANAGE}

    @extend_schema(operation_id="integrations_webhook_detail", responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, pk: str) -> Response:
        endpoint = get_object_or_404(WebhookEndpoint, pk=pk, tenant=require_tenant())
        return Response(
            {
                **_hook(endpoint),
                "deliveries": [
                    {
                        "id": str(d.pk),
                        "event": d.event,
                        "status": d.status,
                        "attempts": d.attempts,
                        "response_code": d.response_code,
                        "error": d.error,
                        "created_at": d.created_at,
                    }
                    for d in endpoint.deliveries.all()[:50]
                ],
            }
        )

    @extend_schema(request=None, responses={204: None})
    def delete(self, request: Request, pk: str) -> Response:
        endpoint = get_object_or_404(WebhookEndpoint, pk=pk, tenant=require_tenant())
        record_platform_event(
            action="developer.webhook_removed",
            request=request,
            tenant=endpoint.tenant,
            data={"url": endpoint.url},
        )
        endpoint.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- The read API for other systems -------------------------------------------------------


class ApiKeyAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request: Request) -> tuple[Any, ApiKey] | None:
        header = request.headers.get("Authorization", "")
        if not header.startswith(f"{self.keyword} {developer.KEY_PREFIX}"):
            return None
        key = developer.find_key(header[len(self.keyword) + 1 :].strip())
        if key is None:
            raise exceptions.AuthenticationFailed("Unknown, revoked or switched-off API key.")
        return (KeyUser(key), key)

    def authenticate_header(self, request: Request) -> str:
        return self.keyword


class ApiKeyScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    """Documents API keys in the OpenAPI schema as a bearer token."""

    target_class = "control_plane.api.developer.ApiKeyAuthentication"
    name = "NexEduApiKey"

    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        return {"type": "http", "scheme": "bearer", "bearerFormat": "nxk_<prefix>_<secret>"}


class KeyUser:
    """Who a key call is: not a person, so no school role applies."""

    is_authenticated = True
    is_active = True

    def __init__(self, key: ApiKey) -> None:
        self.pk = None
        self.key = key


class HasScope(BasePermission):
    message = "This key can't read that."

    def has_permission(self, request: Request, view: Any) -> bool:
        key = request.auth
        return isinstance(key, ApiKey) and view.scope in key.scopes


class KeyThrottle(SimpleRateThrottle):
    scope = "developer"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        key = request.auth
        return f"throttle_developer_{key.pk}" if isinstance(key, ApiKey) else None


class KeyView(APIView):
    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasScope]
    throttle_classes = [KeyThrottle]
    tenant_scoped = False
    scope = ""
    LIMIT = 200

    def rows(self, request: Request) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get(self, request: Request) -> Response:
        key: ApiKey = request.auth  # type: ignore[assignment]
        other = getattr(request, "tenant", None)
        if other is not None and other.pk != key.tenant_id:
            raise exceptions.PermissionDenied("This key belongs to another school.")
        with tenant_context(key.tenant):
            rows = self.rows(request)
        return Response({"school": key.tenant.slug, "count": len(rows), "results": rows})


def _since(request: Request) -> dt.datetime | None:
    raw = request.query_params.get("since")
    if not raw:
        return None
    try:
        value = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise exceptions.ValidationError({"since": "Use an ISO 8601 date and time."}) from exc
    return value if value.tzinfo else timezone.make_aware(value)


SINCE = OpenApiParameter("since", OpenApiTypes.DATETIME, description="Only changes after this")


class DevStudentsView(KeyView):
    """Pupils (?status=active|left|graduated, ?since=). Up to 200, oldest first."""

    scope = "students:read"

    @extend_schema(parameters=[SINCE], responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return super().get(request)

    def rows(self, request: Request) -> list[dict[str, Any]]:
        from apps.students.models import Student

        qs = Student.objects.select_related("arm__level").order_by("created_at")
        if value := request.query_params.get("status"):
            qs = qs.filter(status=value)
        if since := _since(request):
            qs = qs.filter(created_at__gt=since)
        return [
            {
                "id": str(s.pk),
                "admission_number": s.admission_number,
                "first_name": s.first_name,
                "last_name": s.last_name,
                "class": str(s.arm) if s.arm else None,
                "status": s.status,
                "admitted_on": s.admitted_on,
                "created_at": s.created_at,
            }
            for s in qs[: self.LIMIT]
        ]


class DevClassesView(KeyView):
    scope = "classes:read"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return super().get(request)

    def rows(self, request: Request) -> list[dict[str, Any]]:
        from apps.academics.models import ClassArm, Subject

        subjects = list(Subject.objects.order_by("name").values_list("name", flat=True))
        return [
            {"id": a.pk, "name": str(a), "level": a.level.name, "subjects": subjects}
            for a in ClassArm.objects.select_related("level").order_by("level__order", "name")
        ]


class DevAttendanceView(KeyView):
    """Marks for one day (?date=YYYY-MM-DD, default today)."""

    scope = "attendance:read"

    @extend_schema(
        parameters=[OpenApiParameter("date", OpenApiTypes.DATE)], responses=OpenApiTypes.OBJECT
    )
    def get(self, request: Request) -> Response:
        return super().get(request)

    def rows(self, request: Request) -> list[dict[str, Any]]:
        from apps.attendance.models import AttendanceRecord

        try:
            day = dt.date.fromisoformat(
                request.query_params.get("date") or timezone.localdate().isoformat()
            )
        except ValueError as exc:
            raise exceptions.ValidationError({"date": "Use YYYY-MM-DD."}) from exc
        return [
            {
                "student_id": str(r.student_id),
                "admission_number": r.student.admission_number,
                "class": str(r.arm),
                "date": r.date,
                "status": r.status,
            }
            for r in AttendanceRecord.objects.filter(date=day).select_related(
                "student", "arm__level"
            )[:2000]
        ]


class DevPaymentsView(KeyView):
    """Fee payments received (?since=), oldest first."""

    scope = "finance:read"

    @extend_schema(parameters=[SINCE], responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return super().get(request)

    def rows(self, request: Request) -> list[dict[str, Any]]:
        from apps.finance.models import Payment

        qs = (
            Payment.objects.filter(status=Payment.Status.SUCCESS)
            .select_related("invoice__student")
            .order_by("paid_at")
        )
        if since := _since(request):
            qs = qs.filter(paid_at__gt=since)
        return [payment_data(p) for p in qs[: self.LIMIT]]


def payment_data(p: Any) -> dict[str, Any]:
    return {
        "id": str(p.pk),
        "invoice_number": p.invoice.number,
        "admission_number": p.invoice.student.admission_number,
        "amount_pesewas": p.amount_received_pesewas,
        "currency": "GHS",
        "method": p.method,
        "reference": p.reference,
        "paid_at": p.paid_at,
    }


class DevInvoicesView(KeyView):
    """Fee invoices (?since=), oldest first."""

    scope = "finance:read"

    @extend_schema(parameters=[SINCE], responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return super().get(request)

    def rows(self, request: Request) -> list[dict[str, Any]]:
        from apps.finance.models import Invoice

        qs = Invoice.objects.select_related("student", "term").order_by("created_at")
        if since := _since(request):
            qs = qs.filter(created_at__gt=since)
        return [
            {
                "id": str(i.pk),
                "number": i.number,
                "admission_number": i.student.admission_number,
                "term": str(i.term),
                "status": i.status,
                "total_pesewas": i.total_pesewas,
                "paid_pesewas": i.paid_pesewas,
                "due_date": i.due_date,
                "currency": "GHS",
            }
            for i in qs.select_related("term__session")[: self.LIMIT]
        ]
