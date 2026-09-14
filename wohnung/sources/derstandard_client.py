from __future__ import annotations

import re

from wohnung.energy import sniff_energy
from wohnung.fetch import Fetcher
from wohnung.floors import parse_floor
from wohnung.models import Listing
from wohnung.sources import derstandard as ds
from wohnung.sources.availability import sniff_available

SEARCH_URLS = {
    "rent": "https://immobilien.derstandard.at/suche/wien/mieten-wohnung",
    "buy": "https://immobilien.derstandard.at/suche/wien/kaufen-wohnung",
}
# Listing photos (the /plain/ path on the image CDN); avoids the _next/static assets
# served from the sibling s.prod host.
_IMG_RE = re.compile(
    r"https://(?:i\.prod\.mp-dst\.onyx60\.com/plain/|ic\.ds\.at/|storage\.justimmo\.at/)[^\s\"'\\)]+",
    re.I,
)
_FLOOR_RE = re.compile(r"\b(\d{1,2})\.\s*(?:Stock|OG|Etage|Geschoss)\b|\b(Erdgeschoss|Dachgeschoss|Hochparterre)\b", re.I)


class DerStandardSource:
    name = "derstandard"

    def __init__(self, fetcher: Fetcher, mode: str = "rent"):
        self.f = fetcher
        self.mode = mode
        self.search_url = SEARCH_URLS[mode]

    def _stamp(self, listing: Listing) -> Listing:
        if self.mode == "buy":
            listing.price_kind = "kauf"
        listing.floor_number = parse_floor(listing.floor)
        return listing

    def search(self, max_pages: int = 3) -> list[Listing]:
        out: list[Listing] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            params = {"page": page} if page > 1 else None
            try:
                html = self.f.get(self.search_url, params=params)
            except Exception:
                break  # keep results gathered so far; a page failure ends pagination
            page_listings = ds.parse_search(html)
            fresh = [l for l in page_listings if l.id not in seen]
            if not fresh:
                break
            seen.update(l.id for l in fresh)
            out.extend(self._stamp(l) for l in fresh)
        return out

    def enrich(self, listing: Listing) -> Listing:
        html = self.f.get(listing.url)
        text = re.sub(r"<[^>]+>", " ", html)
        # postcode/district: reliably present on the detail page ("... in 1030 Wien ...")
        if listing.district is None:
            pc = re.search(r"\b(1\d{3})\s*Wien", text)
            if pc:
                listing.postcode = int(pc.group(1))
                listing.district = int(pc.group(1)[1:3])
        # elevator: detail text only (cards don't carry it); keep unknown if absent
        if re.search(r"\b(aufzug|lift|personenaufzug)\b", text, re.I):
            listing.has_elevator = True
        listing.available_from = sniff_available(text) or listing.available_from
        if not listing.floor:
            m = _FLOOR_RE.search(text)
            if m:
                listing.floor = m.group(0)
        if not listing.energy_class:
            listing.energy_class, hwb = sniff_energy(text)
            listing.hwb = listing.hwb if listing.hwb is not None else hwb
        imgs = [u for u in dict.fromkeys(_IMG_RE.findall(html)) if "logo" not in u.lower()]
        if imgs:
            listing.image_urls = imgs[:12]
        if not listing.description:
            listing.description = listing.title
        return self._stamp(listing)
