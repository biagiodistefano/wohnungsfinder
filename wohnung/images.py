from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from wohnung.fetch import Fetcher
from wohnung.models import Listing


def is_isobmff(data: bytes) -> bool:
    """True for AVIF/HEIF containers (ISO base media 'ftyp' box), which some portals serve
    under a .jpg name. Image viewers that only accept PNG/JPEG can't open them."""
    return len(data) >= 12 and data[4:8] == b"ftyp"


def convert_to_jpeg(path: Path) -> bool:
    """Convert an AVIF/HEIF file to JPEG in place (macOS `sips`). Returns True on success;
    on failure the original is left untouched (the skill then just skips that photo)."""
    if not shutil.which("sips"):
        return False
    tmp = path.with_name(path.stem + ".conv.jpg")
    try:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(path), "--out", str(tmp)],
            check=True, capture_output=True, timeout=30,
        )
        tmp.replace(path)
        return True
    except (subprocess.SubprocessError, OSError):
        tmp.unlink(missing_ok=True)
        return False


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
        if is_isobmff(data):
            convert_to_jpeg(p)
        saved.append(str(p))
    listing.local_images = saved
    return saved
