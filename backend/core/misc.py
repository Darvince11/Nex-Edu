"""Small shared helpers: client IP, tenant cache keys."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest

from control_plane.tenancy import require_tenant


def client_ip(request: HttpRequest) -> str:
    """The client IP, trusting only the configured number of proxies (ALB, CloudFront)."""
    trusted = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if trusted and forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if len(hops) >= trusted:
            return hops[-trusted]
    return str(request.META.get("REMOTE_ADDR", ""))


def tenant_cache_key(*parts: object) -> str:
    """Cache keys are always namespaced by school."""
    return ":".join(["t", require_tenant().slug, *map(str, parts)])
