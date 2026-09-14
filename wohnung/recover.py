"""Rebuild lost dedup state (state/seen.json) from past reports.

If seen.json is deleted or emptied, every listing re-surfaces as "new" on the next run.
The reports we keep in ``reports/*.md`` — and the latest ``reports/.last_run.json`` —
record the listing URLs (and, in the JSON, full fields) we already processed. This maps
those back to listing ids so a wipe is one command (``wohnung reindex``) to recover.

Recovery is best-effort and never destructive: it only *adds* ids the state doesn't
already have, leaving genuine statuses (interested/rejected/…) untouched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from wohnung.dedup import fingerprint_from, meta_price
from wohnung.state import State

_HREF = re.compile(r'href="([^"]+)"')
_BARE = re.compile(r"https?://[^\s\"'<>)]+")


def id_from_url(url: str) -> Optional[str]:
    """Map a listing URL back to its source-prefixed id, matching how each source
    builds ids (see wohnung/sources/*). Returns None for unrecognised URLs."""
    u = url.strip().rstrip('">).,')
    path = u.split("?")[0].split("#")[0]
    if "willhaben.at" in u:
        m = re.search(r"-(\d+)/?$", path)  # id is the trailing -<digits> of the slug
        if m:
            return f"willhaben_{m.group(1)}"
    if "immobilienscout24.at" in u:
        m = re.search(r"/expose/([0-9a-fA-F]+)", path)
        if m:
            return f"immoscout_{m.group(1)}"
    if "immowelt.at" in u:
        m = re.search(r"/expose/([0-9a-fA-F-]+)", path)  # uuid (with dashes)
        if m:
            return f"immowelt_{m.group(1)}"
    if "derstandard.at" in u:
        m = re.search(r"/detail/(\d+)", path)
        if m:
            return f"derstandard_{m.group(1)}"
    return None


def ids_from_text(text: str) -> dict[str, str]:
    """Extract {listing_id: url} from arbitrary report text (href attrs + bare URLs)."""
    out: dict[str, str] = {}
    for url in set(_HREF.findall(text)) | set(_BARE.findall(text)):
        lid = id_from_url(url)
        if lid and lid not in out:
            out[lid] = url.strip().rstrip('">).,')
    return out


def _records_from_last_run(path: Path) -> dict[str, dict]:
    """Richer recovery from .last_run.json: ids plus fingerprint inputs (meta)."""
    recs: dict[str, dict] = {}
    if not path.exists():
        return recs
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return recs
    for bucket in ("new_listings", "duplicates", "excluded"):
        for item in data.get(bucket, []):
            lid = item.get("id") or id_from_url(item.get("url", ""))
            if not lid:
                continue
            meta = {
                k: item.get(k)
                for k in ("district", "rooms", "size_m2", "price", "rent")
                if item.get(k) is not None
            }
            fp = fingerprint_from(
                meta.get("district"), meta.get("rooms"), meta.get("size_m2"), meta_price(meta)
            )
            recs[lid] = {"url": item.get("url", ""), "meta": meta or None, "fingerprint": fp}
    return recs


def reindex(root: Path) -> dict:
    """Rebuild seen.json from every reports/*.md and the latest .last_run.json.

    Returns {"added": n, "scanned": n_ids, "total": len(state)}.
    """
    reports = root / "reports"
    state = State(root / "state" / "seen.json")

    # Collect candidate ids. Start with URL-only ids from all markdown reports, then
    # overlay the richer records (with meta/fingerprint) from .last_run.json.
    found: dict[str, dict] = {}
    for md in sorted(reports.glob("*.md")):
        for lid, url in ids_from_text(md.read_text(encoding="utf-8")).items():
            found.setdefault(lid, {"url": url, "meta": None, "fingerprint": None})
    for lid, rec in _records_from_last_run(reports / ".last_run.json").items():
        found[lid] = rec  # richer; overrides the url-only entry

    added = 0
    for lid, rec in found.items():
        if not state.is_new(lid):
            continue
        source = lid.split("_", 1)[0]
        if state.record(
            lid, source=source, url=rec.get("url", ""), status="seen",
            fingerprint=rec.get("fingerprint"), meta=rec.get("meta"),
        ):
            added += 1

    return {"added": added, "scanned": len(found), "total": len(state)}
