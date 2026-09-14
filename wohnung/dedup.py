"""Cross-source duplicate detection.

The same flat is often cross-posted to several portals (Willhaben, ImmoScout24,
immowelt) under different per-source IDs. Our state dedups by ID, so those would show
up multiple times. A fingerprint of (district, rooms, rounded size, rounded price)
collapses them. Best-effort: if the key fields are missing the listing has NO
fingerprint and is never merged away (kept and shown)."""

from __future__ import annotations

from typing import Optional

from wohnung.models import Listing

# Price rounding step per search mode: cross-posts differ by a few EUR in rent, by a
# few hundred EUR in purchase price.
PRICE_STEP = {"rent": 10, "buy": 1000}


def fingerprint_from(
    district: Optional[int],
    rooms: Optional[float],
    size_m2: Optional[float],
    price: Optional[float],
    mode: str = "rent",
) -> Optional[str]:
    """A stable key for the underlying apartment from its raw fields, or None if we
    can't form one. Kept separate from ``fingerprint`` so persisted records (which store
    these inputs as ``meta``) can recompute the key even if a Listing isn't around —
    e.g. when rebuilding ``_fingerprints`` on load or after the formula changes."""
    if district is None or size_m2 is None or price is None:
        return None
    step = PRICE_STEP.get(mode, 10)
    size = round(size_m2)  # exact-ish; cross-posts share the same area
    p = round(price / step) * step
    r = round(rooms) if rooms is not None else "?"
    return f"{district}|{r}|{size}|{p}"


def fingerprint(l: Listing, mode: str = "rent") -> Optional[str]:
    """A stable key for the underlying apartment, or None if we can't form one."""
    return fingerprint_from(l.district, l.rooms, l.size_m2, l.price, mode=mode)


def meta_price(meta: dict) -> Optional[float]:
    """Price from a persisted meta dict; accepts the legacy 'rent' key."""
    v = meta.get("price")
    return v if v is not None else meta.get("rent")
