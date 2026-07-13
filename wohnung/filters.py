from __future__ import annotations

from wohnung.config import Criteria
from wohnung.models import Listing


def hard_filter(l: Listing, c: Criteria) -> tuple[bool, str]:
    """Return (keep, reason_if_dropped). Elevator/outdoor only drop when EXPLICITLY
    absent (False); unknown (None) is kept and flagged later."""
    if l.district is not None and l.district not in c.include_districts:
        return False, f"district {l.district} excluded"
    if l.rent is not None and l.rent > c.rent_hard_cap:
        return False, f"rent {l.rent:.0f} over cap {c.rent_hard_cap}"
    if l.size_m2 is not None and l.size_m2 < c.min_size_m2:
        return False, f"size {l.size_m2:.0f} below {c.min_size_m2}"
    if l.rooms is not None and l.rooms < c.min_rooms:
        return False, f"rooms {l.rooms:.0f} below {c.min_rooms}"
    if c.musthave_elevator and l.has_elevator is False:
        return False, "no elevator (explicit)"
    if c.musthave_outdoor and l.has_outdoor is False:
        return False, "no outdoor space (explicit)"
    return True, ""
