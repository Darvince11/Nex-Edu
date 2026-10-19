"""Resolves which school a request is for and selects its database.

Resolution order:
1. ``X-Tenant`` header (mobile apps and the API host)
2. Subdomain of ``TENANT_BASE_DOMAIN``, e.g. ``greenfield.nexedu.com.gh``

This only *selects* the school. Whether the user may access it is checked by
``core.permissions.IsTenantMember`` after authentication.
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.cache import patch_cache_control, patch_vary_headers

from control_plane.models import TENANT_SLUG_VALIDATOR, Tenant
from control_plane.provisioning.service import RESERVED_SLUGS
from control_plane.tenancy import tenant_context


def resolve_tenant_slug(request: HttpRequest) -> str | None:
    header = request.headers.get(settings.TENANT_HEADER, "").strip().lower()
    if header:
        return header
    host = request.get_host().split(":", 1)[0].lower()
    suffix = f".{settings.TENANT_BASE_DOMAIN}"
    if host.endswith(suffix):
        label = host[: -len(suffix)]
        if label and "." not in label and label not in RESERVED_SLUGS:
            return label
    return None


class TenantMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.tenant = None  # type: ignore[attr-defined]
        slug = resolve_tenant_slug(request)
        if slug is None:
            return self.get_response(request)

        try:
            TENANT_SLUG_VALIDATOR(slug)
            tenant = Tenant.objects.select_related("cell").get(slug=slug)
        except Exception:
            return JsonResponse(
                {"detail": "School not found.", "code": "tenant_not_found"}, status=404
            )

        if tenant.status != Tenant.Status.ACTIVE:
            return JsonResponse(
                {"detail": "This school is not available.", "code": "tenant_unavailable"},
                status=403,
            )

        request.tenant = tenant  # type: ignore[attr-defined]
        with tenant_context(tenant):
            response = self.get_response(request)

        # School data must never be shared through a cache between schools or users.
        patch_vary_headers(response, [settings.TENANT_HEADER, "Authorization", "Cookie"])
        if "Cache-Control" not in response:
            patch_cache_control(response, private=True, no_store=True)
        return response
