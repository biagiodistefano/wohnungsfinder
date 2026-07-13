from __future__ import annotations

from pathlib import Path

from wohnung.fetch import Fetcher
from wohnung.models import Listing


def download_images(listing: Listing, fetcher: Fetcher, dest_root: Path, limit: int = 6) -> list[str]:
    dest = dest_root / listing.id
    dest.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for i, url in enumerate(listing.image_urls[:limit]):
        try:
            data = fetcher.get_bytes(url)
        except Exception:
            continue
        ext = ".png" if ".png" in url.lower() else ".jpg"
        p = dest / f"{i:02d}{ext}"
        p.write_bytes(data)
        saved.append(str(p))
    listing.local_images = saved
    return saved
