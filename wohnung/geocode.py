"""Address -> (lat, lng) via OpenStreetMap Nominatim, with a local cache.

Used to backfill coordinates for sources that don't provide them (immowelt, derStandard)
so U-Bahn proximity can be computed. Strictly best-effort: any failure (network, rate
limit, no match, missing address) returns None and the caller keeps the listing with
U-Bahn unknown. Never raises to the caller, never excludes a listing.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy asks for an identifiable User-Agent with contact info.
# Set [geocode].contact in criteria.toml (the /setup interview asks for it).
DEFAULT_UA = "wohnungsfinder/0.1 (personal apartment search)"


class Geocoder:
    def __init__(self, cache_path: Path, min_interval: float = 1.1, contact: str | None = None):
        self.ua = (
            f"wohnungsfinder/0.1 (personal apartment search; contact {contact})"
            if contact
            else DEFAULT_UA
        )
        self.cache_path = Path(cache_path)
        self._cache: dict[str, Optional[list]] = {}
        if self.cache_path.exists():
            try:
                self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}
        self._min_interval = min_interval  # Nominatim policy: <= 1 req/sec
        self._last = 0.0

    def lookup(self, query: str) -> Optional[tuple[float, float]]:
        """Return (lat, lng) or None. Cached (including negative results)."""
        if not query:
            return None
        if query in self._cache:
            c = self._cache[query]
            return (c[0], c[1]) if c else None
        coords = None
        try:
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            r = httpx.get(
                NOMINATIM,
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "at"},
                headers={"User-Agent": self.ua},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            if data:
                coords = (float(data[0]["lat"]), float(data[0]["lon"]))
        except Exception:
            coords = None  # graceful: caller keeps listing, U-Bahn stays unknown
        self._cache[query] = list(coords) if coords else None
        self._save()
        return coords

    def _save(self):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass


def query_for(listing) -> str:
    """Build the best geocoding query we can from a listing (street if known, else
    postcode + Wien). Returns '' if there's nothing usable."""
    parts = []
    if getattr(listing, "address", ""):
        parts.append(listing.address)
    if getattr(listing, "postcode", None):
        parts.append(f"{listing.postcode} Wien")
    elif getattr(listing, "district", None):
        parts.append("Wien")
    if not parts:
        return ""
    return ", ".join(parts) + ", Austria"
