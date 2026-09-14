"""ImmoScout24.at parser.

Listing data is embedded in `window.__INITIAL_STATE__` (a JS object, not pure JSON:
it contains bare `undefined` tokens that we replace with `null`). Search hits live at
reduxAsyncConnect.pageData.results.hits[]. Each hit carries price/area/rooms/address/
coords/isPrivate directly, so no detail fetch is needed for hard filtering.
"""

from __future__ import annotations

import json
import re

from wohnung.models import Listing

_STATE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*")
_UNDEF_RE = re.compile(r"\bundefined\b")
ELEVATOR_KW = re.compile(r"\b(aufzug|lift|personenaufzug)\b", re.I)
OUTDOOR_KW = re.compile(r"\b(balkon|terrasse|loggia|garten|freifläche|eigengarten)\b", re.I)


def _load_state(html: str) -> dict | None:
    m = _STATE_RE.search(html)
    if not m:
        return None
    start = html.find("{", m.end())
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(_UNDEF_RE.sub("null", html[start:]))
        return obj
    except (json.JSONDecodeError, ValueError):
        return None


def _district_from_address(addr: str) -> tuple[int | None, int | None]:
    m = re.search(r"\b(1\d{3})\b", addr or "")
    if not m:
        return None, None
    pc = int(m.group(1))
    return pc, int(str(pc)[1:3])


def _to_float(v):
    if isinstance(v, (int, float)):
        return float(v) or None
    return None


def parse_search(html: str) -> list[Listing]:
    state = _load_state(html)
    if not state:
        return []
    hits = (
        state.get("reduxAsyncConnect", {})
        .get("pageData", {})
        .get("results", {})
        .get("hits", [])
    )
    listings: list[Listing] = []
    for hit in hits:
        eid = hit.get("exposeId")
        price = _to_float(hit.get("primaryPrice"))
        area = _to_float(hit.get("primaryArea"))
        if not eid or price is None or area is None:
            continue  # skip developer-project placeholders without concrete figures
        url = (hit.get("links") or {}).get("absoluteURL") or f"https://www.immobilienscout24.at/expose/{eid}"
        pc, district = _district_from_address(hit.get("addressString", ""))
        coords = None
        loc = hit.get("location") or {}
        if loc.get("type") == "POINT" and loc.get("lat") and loc.get("lon"):
            coords = (float(loc["lat"]), float(loc["lon"]))
        pic = (hit.get("primaryPictureImageProps") or {}).get("src")
        imgs = [pic] if pic else []
        listings.append(
            Listing(
                id=f"immoscout_{eid}",
                source="immoscout",
                url=url,
                title=hit.get("headline") or hit.get("addressString", ""),
                address=hit.get("addressString", ""),
                postcode=pc,
                district=district,
                price=price,
                size_m2=area,
                rooms=_to_float(hit.get("numberOfRooms")),
                provisionsfrei=bool(hit.get("isPrivate")) if hit.get("isPrivate") is not None else None,
                coordinates=coords,
                image_urls=imgs,
                raw={"hit": {k: hit.get(k) for k in ("exposeId", "addressString", "displayType")}},
            )
        )
    return listings


def sniff_equipment(text: str) -> tuple[bool | None, bool | None, str]:
    """Best-effort elevator/outdoor detection from detail-page text. Returns
    (has_elevator, has_outdoor, outdoor_desc). None when the page text is empty."""
    if not text:
        return None, None, ""
    has_elev = bool(ELEVATOR_KW.search(text)) or None  # True or unknown (avoid false 'no')
    out = OUTDOOR_KW.findall(text)
    has_out = bool(out) or None
    return has_elev, has_out, ", ".join(sorted({o.lower() for o in out}))
