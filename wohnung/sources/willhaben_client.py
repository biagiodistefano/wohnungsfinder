from __future__ import annotations

from wohnung.fetch import Fetcher
from wohnung.floors import parse_floor
from wohnung.models import Listing
from wohnung.sources import willhaben as wh

SEARCH_URLS = {
    "rent": "https://www.willhaben.at/iad/immobilien/mietwohnungen/wien",
    "buy": "https://www.willhaben.at/iad/immobilien/eigentumswohnung/wien",
}


class WillhabenSource:
    name = "willhaben"

    def __init__(self, fetcher: Fetcher, mode: str = "rent"):
        self.f = fetcher
        self.mode = mode
        self.search_url = SEARCH_URLS[mode]

    def _stamp(self, listing: Listing) -> Listing:
        if self.mode == "buy":
            listing.price_kind = "kauf"
        listing.floor_number = parse_floor(listing.floor)
        return listing

    def search(self, max_pages: int = 3, rows: int = 50) -> list[Listing]:
        out: list[Listing] = []
        for page in range(1, max_pages + 1):
            try:
                html = self.f.get(self.search_url, params={"rows": rows, "page": page, "sort": 1})
            except Exception:
                break  # keep results gathered so far; a page failure ends pagination
            page_listings = wh.parse_search(html)
            if not page_listings:
                break
            out.extend(self._stamp(l) for l in page_listings)
        return out

    def enrich(self, listing: Listing) -> Listing:
        html = self.f.get(listing.url)
        det = wh.parse_detail(html, base_id=listing.id)
        listing.description = det.description or listing.description
        listing.building_condition = det.building_condition
        listing.available_from = det.available_from
        listing.has_elevator = det.has_elevator
        listing.has_outdoor = det.has_outdoor
        listing.outdoor = det.outdoor
        if det.image_urls:
            listing.image_urls = det.image_urls
        listing.floor = det.floor or listing.floor
        listing.energy_class = listing.energy_class or det.energy_class
        listing.hwb = listing.hwb if listing.hwb is not None else det.hwb
        return self._stamp(listing)
