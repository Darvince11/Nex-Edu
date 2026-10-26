"""Subscription price bands. No free trial (owner's decision, 24 Oct 2026).

A school's band follows its number of active pupils. The bands live in the
database (``PriceBandSetting``) so the Super Admin can adjust prices in the
console; ``DEFAULT_BANDS`` are the owner's starting prices, used to seed them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PriceBand:
    code: str
    label: str
    max_pupils: int | None  # None: no upper limit
    price_pesewas: int


DEFAULT_BANDS: tuple[PriceBand, ...] = (
    PriceBand("band_1", "Up to 1,000 pupils", 1000, 25_000),
    PriceBand("band_2", "1,001 to 2,000 pupils", 2000, 35_000),
    PriceBand("band_3", "More than 2,000 pupils", None, 45_000),
)
FREE_TRIAL_DAYS = 0


def price_bands() -> tuple[PriceBand, ...]:
    """The current bands, smallest first. Falls back to the defaults if none are stored."""
    from control_plane.models import PriceBandSetting

    stored = tuple(
        PriceBand(b.code, b.label, b.max_pupils, b.price_pesewas)
        for b in PriceBandSetting.objects.order_by("position")
    )
    return stored or DEFAULT_BANDS


def band_for(pupils: int, bands: tuple[PriceBand, ...] | None = None) -> PriceBand:
    bands = bands or price_bands()
    for band in bands:
        if band.max_pupils is None or pupils <= band.max_pupils:
            return band
    return bands[-1]


def band_dict(pupils: int, bands: tuple[PriceBand, ...] | None = None) -> dict[str, Any]:
    return asdict(band_for(pupils, bands))
