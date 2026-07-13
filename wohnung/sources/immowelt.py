"""immowelt.at parser.

The search page (/liste/wien/wohnungen/mieten) server-renders ~30 listing cards. Each
card's covering-link anchor carries a rich `title` with everything we need, e.g.:
    "Wohnung zur Miete - Erstbezug - Wien,Donaustadt - 1.152 € - 1,5 Zimmer, 71,6 m²,
     4. Geschoss, frei ab 01.07.2026"
plus href="https://www.immowelt.at/expose/<id>". Deeper pagination is JS/API-only (the
API 403s on plain HTTP), so we take the first page (~30 newest) per run. District and
elevator/outdoor come from the detail page (no coordinates anywhere — geocoded later).
"""

from __future__ import annotations

import re

from wohnung.models import Listing

BASE = "https://www.immowelt.at"
_ANCHOR_RE = re.compile(
    r'<a\s+href="https://www\.immowelt\.at/expose/([0-9a-f-]{8,})"[^>]*?title="([^"]+)"',
    re.I,
)
_PRICE_RE = re.compile(r"-\s*([\d.]+)\s*€")
_ROOMS_RE = re.compile(r"([\d,]+)\s*Zimmer")
_SIZE_RE = re.compile(r"([\d.,]+)\s*m²")
_FLOOR_RE = re.compile(r"([\w.]+)\.\s*Geschoss")
_AVAIL_RE = re.compile(r"frei ab\s*([\d.]{8,10})")


def _de_int(s: str) -> float | None:
    try:
        return float(s.replace(".", ""))  # "1.152" -> 1152
    except ValueError:
        return None


def _de_dec(s: str) -> float | None:
    try:
        return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)
    except ValueError:
        return None


def parse_search(html: str) -> list[Listing]:
    listings: list[Listing] = []
    seen: set[str] = set()
    for m in _ANCHOR_RE.finditer(html):
        eid, title = m.group(1), m.group(2)
        if eid in seen or "m²" not in title:
            continue
        seen.add(eid)
        price = _PRICE_RE.search(title)
        rooms = _ROOMS_RE.search(title)
        size = _SIZE_RE.search(title)
        floor = _FLOOR_RE.search(title)
        avail = _AVAIL_RE.search(title)
        listings.append(
            Listing(
                id=f"immowelt_{eid}",
                source="immowelt",
                url=f"{BASE}/expose/{eid}",
                title=title,
                rent=_de_int(price.group(1)) if price else None,
                rooms=_de_dec(rooms.group(1)) if rooms else None,
                size_m2=_de_dec(size.group(1)) if size else None,
                floor=floor.group(1) if floor else "",
                available_from=avail.group(1) if avail else "",
                raw={"title": title},
            )
        )
    return listings
