"""Vienna district names -> numbers, for sources that only name the Bezirk in text."""

from __future__ import annotations

import re

DISTRICTS = {
    "innere stadt": 1, "leopoldstadt": 2, "landstraße": 3, "landstrasse": 3, "wieden": 4,
    "margareten": 5, "mariahilf": 6, "neubau": 7, "josefstadt": 8, "alsergrund": 9,
    "favoriten": 10, "simmering": 11, "meidling": 12, "hietzing": 13, "penzing": 14,
    "rudolfsheim-fünfhaus": 15, "rudolfsheim-fuenfhaus": 15, "ottakring": 16, "hernals": 17,
    "währing": 18, "waehring": 18, "döbling": 19, "doebling": 19, "brigittenau": 20,
    "floridsdorf": 21, "donaustadt": 22, "liesing": 23,
}
_NAMES = "|".join(re.escape(k) for k in sorted(DISTRICTS, key=len, reverse=True))
# "Neubau" is both a district and a building type, so prefer the positions where portals
# put the Bezirk: after "Wien," or between " - " separators; bare match is the fallback.
_ANCHORED_RE = re.compile(rf"(?:\bWien\s*,\s*|(?<=\s-\s))({_NAMES})(?=\s*(?:-|,|$))", re.I)
_BARE_RE = re.compile(rf"\b({_NAMES})\b", re.I)


def district_from_name(text: str) -> int | None:
    """Vienna district named in `text`, as a number; None if none."""
    # Last anchored match wins: building-type words ("Neubau") precede the Bezirk slot.
    for rx in (_ANCHORED_RE, _BARE_RE):
        found = rx.findall(text or "")
        if found:
            return DISTRICTS[found[-1].lower()]
    return None
