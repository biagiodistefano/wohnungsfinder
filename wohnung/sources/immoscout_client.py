from __future__ import annotations

import re

from wohnung.fetch import Fetcher
from wohnung.floors import parse_floor
from wohnung.models import Listing
from wohnung.sources import immoscout as im
from wohnung.sources.availability import sniff_available

SEARCH_URLS = {
    "rent": "https://www.immobilienscout24.at/regional/wien/wien/wohnung-mieten",
    "buy": "https://www.immobilienscout24.at/regional/wien/wien/wohnung-kaufen",
}
# IS24 photo URLs have no file extension (loadPicture?id=... / dims3 transforms).
_IMG_RE = re.compile(r"https://pictures\.immobilienscout24\.de/[^\s\"'\\)]+", re.I)


class ImmoScoutSource:
    name = "immoscout"

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
            url = self.search_url if page == 1 else f"{self.search_url}/seite-{page}"
            try:
                html = self.f.get(url)
            except Exception:
                break  # keep results gathered so far; a page failure ends pagination
            page_listings = im.parse_search(html)
            fresh = [l for l in page_listings if l.id not in seen]
            if not fresh:
                break
            seen.update(l.id for l in fresh)
            out.extend(self._stamp(l) for l in fresh)
        return out

    def enrich(self, listing: Listing) -> Listing:
        html = self.f.get(listing.url)
        text = re.sub(r"<[^>]+>", " ", html)
        has_elev, has_out, outdoor = im.sniff_equipment(text)
        listing.has_elevator = has_elev
        listing.has_outdoor = has_out
        listing.outdoor = outdoor
        listing.available_from = sniff_available(text) or listing.available_from
        d = im.sniff_detail(html)
        listing.floor = listing.floor or d["floor"]
        listing.energy_class = listing.energy_class or d["energy_class"]
        listing.hwb = listing.hwb if listing.hwb is not None else d["hwb"]
        if d["year_built"]:
            listing.raw["year_built"] = d["year_built"]
        imgs = list(dict.fromkeys(u.replace("&amp;", "&") for u in _IMG_RE.findall(html)))
        if imgs:
            listing.image_urls = imgs[:12]
        return self._stamp(listing)
