from __future__ import annotations

from django.utils import timezone

from control_plane.tenancy import tenant_atomic

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
