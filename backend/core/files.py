"""School files (report cards, receipts, uploads) under a per-school prefix.

Keys are always ``tenants/<slug>/...``. In production the storage is S3 with
SSE-KMS, the app's IAM role can reach only that prefix, and downloads are
short-lived presigned URLs. Locally it is the filesystem.
"""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponse, HttpResponseRedirect, JsonResponse

from control_plane.tenancy import require_tenant


def tenant_key(relative: str) -> str:
    relative = relative.lstrip("/")
    if ".." in relative.split("/"):
        raise ValueError("Path traversal is not allowed")
    return f"tenants/{require_tenant().slug}/{relative}"


def save_tenant_file(relative: str, content: bytes) -> str:
    key = tenant_key(relative)
    if default_storage.exists(key):
        default_storage.delete(key)
    return default_storage.save(key, ContentFile(content))


def tenant_file_response(
    key: str, *, filename: str, content_type: str, as_link: bool = False
) -> HttpResponse:
    """Stream the file, or (on S3) hand out a 5-minute presigned URL.

    ``as_link`` returns ``{"url": ...}`` as JSON instead of a redirect, so a
    browser app under a strict CSP can navigate to S3 rather than fetch it.
    """
    if not key.startswith(f"tenants/{require_tenant().slug}/"):
        raise PermissionError("File belongs to another school")
    if getattr(default_storage, "querystring_auth", False):
        url = default_storage.url(
            key,
            parameters={
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
                "ResponseContentType": content_type,
            },
        )
        if as_link:
            return JsonResponse({"url": url})
        return HttpResponseRedirect(url)
    response = FileResponse(default_storage.open(key, "rb"), content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
