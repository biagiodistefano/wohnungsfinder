from __future__ import annotations

from wohnung.config import Criteria
from wohnung.models import Listing


def hard_filter(l: Listing, c: Criteria) -> tuple[bool, str]:
    """Return (keep, reason_if_dropped). Elevator/outdoor/floor only drop when EXPLICITLY
    absent or below (unknown is kept and flagged later)."""
    if l.district is not None and l.district not in c.include_districts:
        return False, f"district {l.district} excluded"
    if l.price is not None and l.price > c.price_hard_cap:
        return False, f"price {l.price:.0f} over cap {c.price_hard_cap}"
    if l.size_m2 is not None and l.size_m2 < c.min_size_m2:
        return False, f"size {l.size_m2:.0f} below {c.min_size_m2}"
    if l.rooms is not None and l.rooms < c.min_rooms:
        return False, f"rooms {l.rooms:.0f} below {c.min_rooms}"
    if c.musthave_elevator and l.has_elevator is False:
        return False, "no elevator (explicit)"
    if c.musthave_outdoor and l.has_outdoor is False:
        return False, "no outdoor space (explicit)"
    if c.min_floor and l.floor_number is not None and l.floor_number < c.min_floor:
        return False, f"floor {l.floor_number} below {c.min_floor} (explicit)"
    return True, ""
