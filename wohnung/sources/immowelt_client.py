from __future__ import annotations

import re

from wohnung.energy import sniff_energy
from wohnung.fetch import Fetcher
from wohnung.floors import parse_floor
from wohnung.models import Listing
from wohnung.sources import immowelt as iw
from wohnung.sources.availability import sniff_available

SEARCH_URLS = {
    "rent": "https://www.immowelt.at/liste/wien/wohnungen/mieten",
    "buy": "https://www.immowelt.at/liste/wien/wohnungen/kaufen",
}
_IMG_RE = re.compile(r"https://cdnihddipa\.cloudimg\.io/[^\s\"'\\)]+", re.I)
_ELEV_RE = re.compile(r"\b(aufzug|lift|personenaufzug)\b", re.I)
_OUT_RE = re.compile(r"\b(balkon|terrasse|loggia|garten|eigengarten|freifläche)\b", re.I)


class ImmoweltSource:
    name = "immowelt"

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
        # Only the first page is available via plain HTTP (pagination is JS/API-only).
        html = self.f.get(self.search_url)
        return [self._stamp(l) for l in iw.parse_search(html)]

    def enrich(self, listing: Listing) -> Listing:
        html = self.f.get(listing.url)
        text = re.sub(r"<[^>]+>", " ", html)
        # postcode/district (reliably on the detail page: "... 1080 Wien ...")
        if listing.district is None:
            pc = re.search(r"\b(1\d{3})\s*Wien", text) or re.search(r"\bWien\b.*?\b(1\d{3})\b", text)
            if pc:
                listing.postcode = int(pc.group(1))
                listing.district = int(pc.group(1)[1:3])
        if _ELEV_RE.search(text):
            listing.has_elevator = True
        out = _OUT_RE.findall(text)
        if out:
            listing.has_outdoor = True
            listing.outdoor = ", ".join(sorted({o.lower() for o in out}))
        listing.available_from = listing.available_from or sniff_available(text)
        if not listing.energy_class:
            listing.energy_class, hwb = sniff_energy(text)
            listing.hwb = listing.hwb if listing.hwb is not None else hwb
        imgs = list(dict.fromkeys(_IMG_RE.findall(html)))
        if imgs:
            listing.image_urls = imgs[:12]
        return self._stamp(listing)
