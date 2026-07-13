from __future__ import annotations

from typing import Protocol

from wohnung.models import Listing


class Source(Protocol):
    name: str

    def search(self, max_pages: int) -> list[Listing]: ...

    def enrich(self, listing: Listing) -> Listing: ...
