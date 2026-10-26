"""Alumni and fundraising (school leaders). Contact details are only exported for
people who agreed to be contacted (Act 843); gifts received go into the books when
the Accounting module is on."""

from __future__ import annotations

import csv
import io
from typing import Any, ClassVar

from django.db.models import Count, Q, QuerySet, Sum
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.academics.api.views import AuditedCrudViewSet
from apps.students.models import Student
from control_plane.modules import is_active
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm
from core.views import TenantViewSet

from ..models import Alumnus, Gift

MANAGE = Perm.ALUMNI_MANAGE


class AlumnusSerializer(serializers.ModelSerializer[Alumnus]):
    given_pesewas = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Alumnus
        fields: ClassVar = [
            "id",
            "first_name",
            "last_name",
            "class_of",
            "phone",
            "email",
            "occupation",
            "lives_in",
            "may_contact",
            "consent_recorded_at",
            "notes",
            "given_pesewas",
        ]
        read_only_fields: ClassVar = ["consent_recorded_at"]
        extra_kwargs: ClassVar = {"class_of": {"min_value": 1950, "max_value": 2100}}

    def _consent(self, validated: dict[str, Any], instance: Alumnus | None) -> None:
        if validated.get("may_contact") and not (instance and instance.may_contact):
            validated["consent_recorded_at"] = timezone.now()
        if validated.get("may_contact") is False:
            validated["consent_recorded_at"] = None

    def create(self, validated_data: dict[str, Any]) -> Alumnus:
        self._consent(validated_data, None)
        return super().create(validated_data)

    def update(self, instance: Alumnus, validated_data: dict[str, Any]) -> Alumnus:
        self._consent(validated_data, instance)
        return super().update(instance, validated_data)


class AlumnusViewSet(AuditedCrudViewSet):
    serializer_class = AlumnusSerializer
    audit_name = "alumnus"
    required_permissions: ClassVar = {
        k: MANAGE
        for k in (
            "list",
            "retrieve",
            "create",
            "update",
            "partial_update",
            "destroy",
            "import_graduates",
            "mailing_list",
        )
    }

    def get_queryset(self) -> QuerySet[Alumnus]:
        qs = Alumnus.objects.annotate(
            given_pesewas=Sum("gifts__amount_pesewas", filter=Q(gifts__kind=Gift.Kind.RECEIVED))
        )
        params = self.request.query_params
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(occupation__icontains=q)
            )
        if (year := params.get("class_of", "")).isdigit():
            qs = qs.filter(class_of=int(year))
        return qs

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def import_graduates(self, request: Request) -> Response:
        """Add every graduated pupil not yet on the list (they still need to agree to contact)."""
        year = timezone.localdate().year
        added = 0
        with tenant_atomic():
            for pupil in Student.objects.filter(
                status=Student.Status.GRADUATED, alumnus__isnull=True
            ):
                Alumnus.objects.create(
                    student=pupil,
                    first_name=pupil.first_name,
                    last_name=pupil.last_name,
                    class_of=year,
                )
                added += 1
            record_event(action="alumni.imported", request=request, after={"added": added})
        return Response({"added": added}, status=status.HTTP_201_CREATED)

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.BINARY})
    @action(detail=False, methods=["get"])
    def mailing_list(self, request: Request) -> HttpResponse:
        """Only those who agreed to hear from the school."""
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Name", "Class of", "Phone", "Email"])
        people = Alumnus.objects.filter(may_contact=True)
        for a in people:
            writer.writerow([a.full_name, a.class_of, a.phone, a.email])
        with tenant_atomic():
            record_event(
                action="alumni.exported", request=request, after={"people": people.count()}
            )
        response = HttpResponse(out.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="alumni-mailing-list.csv"'
        return response


class GiftSerializer(serializers.ModelSerializer[Gift]):
    alumnus_name = serializers.CharField(source="alumnus.full_name", read_only=True, default="")

    class Meta:
        model = Gift
        fields: ClassVar = [
            "id",
            "alumnus",
            "alumnus_name",
            "donor",
            "amount_pesewas",
            "kind",
            "date",
            "purpose",
            "in_books",
        ]
        read_only_fields: ClassVar = ["in_books"]
        extra_kwargs: ClassVar = {
            "amount_pesewas": {"min_value": 1, "max_value": 1_000_000_000_00},
            "donor": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get("donor"):
            if not attrs.get("alumnus"):
                raise serializers.ValidationError({"donor": "Say who gave."})
            attrs["donor"] = attrs["alumnus"].full_name
        received = attrs.get("kind", Gift.Kind.RECEIVED) == Gift.Kind.RECEIVED
        if received and attrs["date"] > timezone.localdate():
            raise serializers.ValidationError({"date": "Money received can't be in the future."})
        return attrs


def _into_books(request: Request, gift: Gift) -> None:
    """Received money goes into the books as donation income, when Accounting is on."""
    if gift.kind != Gift.Kind.RECEIVED or not is_active(require_tenant(), "accounting"):
        return
    from apps.accounting import services as accounting
    from apps.finance.models import LedgerAccount

    accounting.ensure_accounts()
    accounting.record(
        request=request,
        kind="income",
        date=gift.date,
        account=LedgerAccount.objects.get(code="4200"),
        amount=gift.amount_pesewas,
        method="cash",
        party=gift.donor,
        description=gift.purpose or "Gift",
    )
    gift.in_books = True
    gift.save(update_fields=["in_books"])


class GiftViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, TenantViewSet):
    serializer_class = GiftSerializer
    queryset = Gift.objects.select_related("alumnus")
    required_permissions: ClassVar = {
        "list": MANAGE,
        "create": MANAGE,
        "received": MANAGE,
        "summary": MANAGE,
    }

    def perform_create(self, serializer: Any) -> None:
        with tenant_atomic():
            gift = serializer.save(recorded_by=self.request.user.pk)
            record_event(
                action="alumni.gift",
                request=self.request,
                target=gift,
                after={
                    "donor": gift.donor,
                    "amount_pesewas": gift.amount_pesewas,
                    "kind": gift.kind,
                },
            )
            _into_books(self.request, gift)

    @extend_schema(request=None, responses=GiftSerializer)
    @action(detail=True, methods=["post"])
    def received(self, request: Request, pk: str | None = None) -> Response:
        """A pledge has been paid."""
        gift = self.get_object()
        if gift.kind == Gift.Kind.RECEIVED:
            return Response(GiftSerializer(gift).data)
        with tenant_atomic():
            gift.kind, gift.date = Gift.Kind.RECEIVED, timezone.localdate()
            gift.save(update_fields=["kind", "date"])
            _into_books(request, gift)
        return Response(GiftSerializer(gift).data)

    @extend_schema(
        parameters=[OpenApiParameter("year", OpenApiTypes.INT)], responses=OpenApiTypes.OBJECT
    )
    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        totals = dict(Gift.objects.values_list("kind").annotate(s=Sum("amount_pesewas")))
        by_purpose = (
            Gift.objects.filter(kind=Gift.Kind.RECEIVED)
            .values("purpose")
            .annotate(total=Sum("amount_pesewas"), n=Count("pk"))
            .order_by("-total")[:10]
        )
        return Response(
            {
                "received_pesewas": totals.get(Gift.Kind.RECEIVED, 0),
                "pledged_pesewas": totals.get(Gift.Kind.PLEDGE, 0),
                "alumni": Alumnus.objects.count(),
                "may_contact": Alumnus.objects.filter(may_contact=True).count(),
                "by_purpose": [
                    {
                        "purpose": r["purpose"] or "General",
                        "total_pesewas": r["total"],
                        "gifts": r["n"],
                    }
                    for r in by_purpose
                ],
            }
        )
