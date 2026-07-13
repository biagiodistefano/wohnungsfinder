"""derStandard Immobilien parser.

The site is a Next.js app whose Flight payload uses indexed references (hard to
parse), but the listing cards are server-rendered in the HTML. Each card ends with
an anchor:
    <a aria-label="TITLE" class="...sc-listing-card-content-background-link..." href="/detail/ID">
and the card's own price / m² / Zimmer / postcode / outdoor keyword appear in the
markup immediately before that anchor. We anchor on the link and read the window
just before it. No coordinates are available in the card (U-Bahn stays unknown).
"""

from __future__ import annotations

import re

from wohnung.models import Listing

BASE = "https://immobilien.derstandard.at"
_ANCHOR_RE = re.compile(
    r'<a\s+aria-label="(?P<title>[^"]*)"[^>]*sc-listing-card-content-background-link[^>]*href="/detail/(?P<id>\d+)"',
    re.S,
)
_PRICE_RE = re.compile(r"€\s*([\d.]+)")
_SIZE_RE = re.compile(r"([\d]+(?:[.,]\d+)?)\s*m²")
_ROOMS_RE = re.compile(r"(\d+)\s*Zimmer")
_PC_RE = re.compile(r"\b(1\d{3})\s*Wien")
OUTDOOR_KW = re.compile(r"(Freifläche|Balkon|Terrasse|Loggia|Garten|Eigengarten)", re.I)


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _last(pattern: re.Pattern, text: str):
    matches = pattern.findall(text)
    return matches[-1] if matches else None


def parse_search(html: str) -> list[Listing]:
    listings: list[Listing] = []
    for m in _ANCHOR_RE.finditer(html):
        did = m.group("id")
        title = m.group("title")
        window = _strip(html[max(0, m.start() - 5000) : m.start()])
        price = _last(_PRICE_RE, window)
        size = _last(_SIZE_RE, window)
        rooms = _last(_ROOMS_RE, window)
        pc = _last(_PC_RE, window)
        out = OUTDOOR_KW.findall(window)
        postcode = int(pc) if pc else None
        listings.append(
            Listing(
                id=f"derstandard_{did}",
                source="derstandard",
                url=f"{BASE}/detail/{did}",
                title=title,
                postcode=postcode,
                district=int(str(postcode)[1:3]) if postcode else None,
                rent=float(price.replace(".", "")) if price else None,
                size_m2=float(size.replace(",", ".")) if size else None,
                rooms=float(rooms) if rooms else None,
                has_outdoor=True if out else None,
                outdoor=", ".join(sorted({o.lower() for o in out})),
                raw={"detail_id": did},
            )
        )
    return listings
