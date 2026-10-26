"""The school's public website: edited by school leaders, read by anyone once published."""

from __future__ import annotations

import re
from typing import Any, ClassVar

from django.utils import timezone
from django.utils.html import strip_tags
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.api.views import AuditedCrudViewSet
from apps.academics.models import CalendarEvent
from apps.school.models import SchoolProfile
from control_plane.modules import is_active
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm
from core.views import PublicEndpointMixin

from ..models import NewsPost, Page, SiteSettings

MANAGE = Perm.WEBSITE_MANAGE
CRUD = ("list", "retrieve", "create", "update", "partial_update", "destroy")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def plain(value: str) -> str:
    """Plain text only: no tags, no control characters."""
    return _CONTROL.sub("", strip_tags(value)).strip()


class PlainTextMixin:
    plain_fields: ClassVar[tuple[str, ...]] = ()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        for name in self.plain_fields:
            if isinstance(attrs.get(name), str):
                attrs[name] = plain(attrs[name])
        return attrs


class SiteSettingsSerializer(PlainTextMixin, serializers.ModelSerializer[SiteSettings]):
    plain_fields = ("tagline", "about", "address", "phone", "office_hours")

    class Meta:
        model = SiteSettings
        fields: ClassVar = [
            "published",
            "tagline",
            "about",
            "address",
            "phone",
            "email",
            "office_hours",
            "show_events",
            "show_admissions",
            "updated_at",
        ]
        read_only_fields: ClassVar = ["updated_at"]


class SiteSettingsView(APIView):
    required_permissions: ClassVar = {"GET": MANAGE, "PATCH": MANAGE}

    @extend_schema(responses=SiteSettingsSerializer)
    def get(self, request: Request) -> Response:
        return Response(SiteSettingsSerializer(SiteSettings.load()).data)

    @extend_schema(request=SiteSettingsSerializer, responses=SiteSettingsSerializer)
    def patch(self, request: Request) -> Response:
        site = SiteSettings.load()
        was_published = site.published
        data = SiteSettingsSerializer(site, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        with tenant_atomic():
            data.save()
            action = "website.updated"
            if site.published != was_published:
                action = "website.published" if site.published else "website.unpublished"
            record_event(action=action, request=request, after=data.data)
        return Response(data.data)


class WebPageSerializer(PlainTextMixin, serializers.ModelSerializer[Page]):
    plain_fields = ("title", "body")

    class Meta:
        model = Page
        fields: ClassVar = ["id", "slug", "title", "body", "order", "published", "updated_at"]
        read_only_fields: ClassVar = ["updated_at"]


class PageViewSet(AuditedCrudViewSet):
    serializer_class = WebPageSerializer
    queryset = Page.objects.all()
    audit_name = "website.page"
    required_permissions: ClassVar = dict.fromkeys(CRUD, MANAGE)


class NewsPostSerializer(PlainTextMixin, serializers.ModelSerializer[NewsPost]):
    plain_fields = ("title", "body")

    class Meta:
        model = NewsPost
        fields: ClassVar = ["id", "title", "body", "date", "published"]


class NewsViewSet(AuditedCrudViewSet):
    serializer_class = NewsPostSerializer
    queryset = NewsPost.objects.all()
    audit_name = "website.news"
    required_permissions: ClassVar = dict.fromkeys(CRUD, MANAGE)


class PublicSiteView(PublicEndpointMixin, APIView):
    """The school's public website (on its own subdomain). Nothing about pupils or
    staff is ever on it: only what the school wrote for the public."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        tenant = getattr(request, "tenant", None)
        if tenant is None or not is_active(tenant, "website"):
            return Response({"detail": "School not found."}, status=404)
        site = SiteSettings.load()
        if not site.published:
            return Response({"detail": "This school's website isn't published yet."}, status=404)
        today = timezone.localdate()
        events = (
            CalendarEvent.objects.filter(
                audience=CalendarEvent.Audience.EVERYONE, ends_on__gte=today
            ).values("title", "kind", "starts_on", "ends_on")[:8]
            if site.show_events
            else []
        )
        return Response(
            {
                "school": SchoolProfile.load().name,
                "tagline": site.tagline,
                "about": site.about,
                "contact": {
                    "address": site.address,
                    "phone": site.phone,
                    "email": site.email,
                    "office_hours": site.office_hours,
                },
                "admissions_open": site.show_admissions and is_active(tenant, "admissions"),
                "pages": list(Page.objects.filter(published=True).values("slug", "title", "body")),
                "news": list(
                    NewsPost.objects.filter(published=True, date__lte=today).values(
                        "title", "body", "date"
                    )[:10]
                ),
                "events": list(events),
            }
        )
