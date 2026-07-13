"""Cross-source duplicate detection.

The same flat is often cross-posted to several portals (Willhaben, ImmoScout24,
immowelt) under different per-source IDs. Our state dedups by ID, so those would show
up multiple times. A fingerprint of (district, rooms, rounded size, rounded price)
collapses them. Best-effort: if the key fields are missing the listing has NO
fingerprint and is never merged away (kept and shown)."""

from __future__ import annotations

from typing import Optional

from wohnung.models import Listing


def fingerprint_from(
    district: Optional[int],
    rooms: Optional[float],
    size_m2: Optional[float],
    rent: Optional[float],
) -> Optional[str]:
    """A stable key for the underlying apartment from its raw fields, or None if we
    can't form one. Kept separate from ``fingerprint`` so persisted records (which store
    these inputs as ``meta``) can recompute the key even if a Listing isn't around —
    e.g. when rebuilding ``_fingerprints`` on load or after the formula changes."""
    if district is None or size_m2 is None or rent is None:
        return None
    size = round(size_m2)  # exact-ish; cross-posts share the same area
    price = round(rent / 10) * 10  # tolerate small price differences
    r = round(rooms) if rooms is not None else "?"
    return f"{district}|{r}|{size}|{price}"


def fingerprint(l: Listing) -> Optional[str]:
    """A stable key for the underlying apartment, or None if we can't form one."""
    return fingerprint_from(l.district, l.rooms, l.size_m2, l.rent)
