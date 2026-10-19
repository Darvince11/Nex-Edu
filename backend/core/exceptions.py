from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from control_plane.tenancy import CrossTenantAccess
from core.crypto import DecryptionError


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Turns tenant-isolation and decryption failures into a plain 403, and Django
    validation errors raised by services into a normal 400."""
    if isinstance(exc, CrossTenantAccess | DecryptionError):
        exc = PermissionDenied("Access denied.")
    elif isinstance(exc, DjangoValidationError):
        detail = exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
        exc = DRFValidationError(detail)
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict) and "code" not in response.data:
        code = getattr(exc, "default_code", None)
        if code:
            response.data["code"] = code
    return response
