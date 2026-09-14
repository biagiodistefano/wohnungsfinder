"""ImmoScout24.at parser.

Listing data is embedded in `window.__INITIAL_STATE__` (a JS object, not pure JSON:
it contains bare `undefined` tokens that we replace with `null`). Search hits live at
reduxAsyncConnect.pageData.results.hits[]. Each hit carries price/area/rooms/address/
coords/isPrivate directly, so no detail fetch is needed for hard filtering.
"""

from __future__ import annotations

import json
import re

from wohnung.energy import sniff_energy
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


def _keyfact_hi(facts: list, unit: str) -> float | None:
    """Upper bound of a range key fact: {'value': '74 – 121 m²', 'label': None} or
    {'value': '2 – 3', 'label': 'Zimmer'}. `unit` matches either the value or the label."""
    for f in facts:
        val, label = str(f.get("value", "")), str(f.get("label") or "")
        if unit.lower() not in (val + " " + label).lower():
            continue
        nums = re.findall(r"\d+(?:[.,]\d+)?", val)
        if nums:
            return float(nums[-1].replace(",", "."))
    return None


_DETAIL_KEYS = {
    "floor": re.compile(r'"floorLabel":\s*"([^"]*)"'),
    "floor_num": re.compile(r'"floor":\s*(\d+)'),
    "energy_class": re.compile(r'"finalEnergyDemandClass":\s*"([A-G])'),
    "hwb": re.compile(r'"finalEnergyDemand":\s*([\d.]+)'),
    "year_built": re.compile(r'"yearOfConstruction":\s*(\d{4})'),
}


def sniff_detail(html: str) -> dict:
    """Pull floor / energy class / build year out of the expose page's embedded JSON.
    Values are often null on IS24; missing -> '' / None. Falls back to text sniffing
    for the energy class."""
    g = {k: (m.group(1) if (m := rx.search(html)) else None) for k, rx in _DETAIL_KEYS.items()}
    floor = g["floor"] or g["floor_num"] or ""
    cls = g["energy_class"] or ""
    hwb = float(g["hwb"]) if g["hwb"] else None
    if not cls:
        cls2, hwb2 = sniff_energy(re.sub(r"<[^>]+>", " ", html))
        cls = cls2
        hwb = hwb if hwb is not None else hwb2
    return {
        "floor": floor,
        "energy_class": cls,
        "hwb": hwb,
        "year_built": int(g["year_built"]) if g["year_built"] else None,
    }


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
        if not eid:
            continue
        rooms = _to_float(hit.get("numberOfRooms"))
        # Developer/Bauträger projects carry no price and only ranges ("74 – 121 m²",
        # "2 – 3 Zimmer"). Keep them flagged; size/rooms take the range's UPPER bound so
        # the hard filter only drops projects that cannot contain a matching unit.
        is_project = price is None or area is None
        if is_project:
            facts = hit.get("mainKeyFacts") or []
            area = area or _keyfact_hi(facts, "m²")
            rooms = rooms or _keyfact_hi(facts, "Zimmer")
        if price is None and not is_project:
            continue  # nothing to filter on
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
                rooms=rooms,
                is_project=is_project,
                provisionsfrei=bool(hit.get("isPrivate")) if hit.get("isPrivate") is not None else None,
                coordinates=coords,
                image_urls=imgs,
                raw={"hit": {k: hit.get(k) for k in ("exposeId", "addressString", "displayType", "mainKeyFacts")}},
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
