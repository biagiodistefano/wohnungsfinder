from __future__ import annotations

from wohnung.fetch import Fetcher
from wohnung.models import Listing
from wohnung.sources import willhaben as wh

SEARCH_URL = "https://www.willhaben.at/iad/immobilien/mietwohnungen/wien"


class WillhabenSource:
    name = "willhaben"

    def __init__(self, fetcher: Fetcher):
        self.f = fetcher

    def search(self, max_pages: int = 3, rows: int = 50) -> list[Listing]:
        out: list[Listing] = []
        for page in range(1, max_pages + 1):
            try:
                html = self.f.get(SEARCH_URL, params={"rows": rows, "page": page, "sort": 1})
            except Exception:
                break  # keep results gathered so far; a page failure ends pagination
            page_listings = wh.parse_search(html)
            if not page_listings:
                break
            out.extend(page_listings)
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
        return listing
