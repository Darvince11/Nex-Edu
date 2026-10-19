from __future__ import annotations

from typing import Any

from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle


class TenantRateThrottle(SimpleRateThrottle):
    """Caps total traffic per school so one school can't starve the others."""

    scope = "tenant"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": tenant.slug}
