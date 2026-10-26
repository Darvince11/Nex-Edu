from __future__ import annotations

from typing import Any

from django.core.files.storage import default_storage
from django.utils import timezone

from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.files import save_tenant_file
from core.images import clean_logo

from .models import Counter, SchoolProfile


def next_number(name: str, *, year: int | None = None) -> tuple[int, int]:
    """Atomically take the next number in a sequence. Returns (year, number).

    The row lock serialises concurrent callers, so two receipts can never share a
    number, even under a fee-deadline payment burst.
    """
    year = year or timezone.localdate().year
    with tenant_atomic():
        counter, _ = Counter.objects.select_for_update().get_or_create(name=name, year=year)
        counter.value += 1
        counter.save(update_fields=["value"])
        return year, counter.value


def formatted_number(name: str, prefix: str, *, width: int = 6) -> str:
    year, number = next_number(name)
    return f"{prefix}-{year}-{number:0{width}d}"


def next_admission_number() -> str:
    profile = SchoolProfile.load()
    year, number = next_number("admission")
    return f"{profile.admission_prefix}/{year}/{number:04d}"


def ensure_profile(name: str) -> SchoolProfile:
    profile, _ = SchoolProfile.objects.get_or_create(pk=1, defaults={"name": name})
    return profile


LOGO_PATH = "branding/logo.png"


def set_logo(*, request: Any, data: bytes) -> SchoolProfile:
    """Validate and re-encode the upload, store it under this school's prefix, audit it."""
    png = clean_logo(data)
    key = save_tenant_file(LOGO_PATH, png)
    with tenant_atomic():
        profile = SchoolProfile.load()
        profile.logo = key
        profile.save(update_fields=["logo", "updated_at"])
        record_event(
            action="school.logo_updated", request=request, target=profile, after={"bytes": len(png)}
        )
    return profile


def remove_logo(*, request: Any) -> SchoolProfile:
    with tenant_atomic():
        profile = SchoolProfile.load()
        if profile.logo:
            default_storage.delete(profile.logo)
            profile.logo = ""
            profile.save(update_fields=["logo", "updated_at"])
            record_event(action="school.logo_removed", request=request, target=profile)
    return profile
