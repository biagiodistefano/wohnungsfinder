"""Willhaben parsers.

Search results: __NEXT_DATA__ -> props.pageProps.searchResult.advertSummaryList.advertSummary[]
Detail page:    __NEXT_DATA__ -> props.pageProps.advertDetails
Equipment (Lift/Balkon/...) lives in advertDetails.attributeInformation[] as a tree
of {treeAttributeElement:{label,code}, values:[{label,code}]}.
"""

from __future__ import annotations

from wohnung.models import Listing
from wohnung.nextdata import extract_next_data

IMG_BASE = "https://cache.willhaben.at/mmo/"
DETAIL_BASE = "https://www.willhaben.at/iad/"
ELEVATOR_CODES = {"LIFT", "ELEVATOR"}
OUTDOOR_CODES = {"BALCONY", "TERRACE", "GARDEN", "LOGGIA", "BALKON", "TERRASSE", "GARTEN"}


def _attrs(ad: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for a in ad.get("attributes", {}).get("attribute", []):
        vals = a.get("values") or []
        out[a["name"]] = vals[0] if vals else ""
    return out


def _num(s):
    try:
        return float(str(s).replace(".", "").replace(",", ".").split()[0]) if "," in str(s) \
            else float(str(s).split()[0])
    except (ValueError, IndexError):
        return None


def parse_search(html: str) -> list[Listing]:
    data = extract_next_data(html)
    if not data:
        return []
    ads = (
        data.get("props", {})
        .get("pageProps", {})
        .get("searchResult", {})
        .get("advertSummaryList", {})
        .get("advertSummary", [])
    )
    listings: list[Listing] = []
    for ad in ads:
        a = _attrs(ad)
        adid = a.get("ADID") or str(ad.get("id", ""))
        if not adid:
            continue
        postcode = int(a["POSTCODE"]) if str(a.get("POSTCODE", "")).isdigit() else None
        district = int(str(postcode)[1:3]) if postcode else None
        coords = None
        if a.get("COORDINATES") and "," in a["COORDINATES"]:
            try:
                lat, lng = a["COORDINATES"].split(",")[:2]
                coords = (float(lat), float(lng))
            except ValueError:
                coords = None
        imgs = [IMG_BASE + p for p in a.get("ALL_IMAGE_URLS", "").split(";") if p]
        seo = a.get("SEO_URL", "")
        listings.append(
            Listing(
                id=f"willhaben_{adid}",
                source="willhaben",
                url=DETAIL_BASE + seo if seo else DETAIL_BASE,
                title=a.get("HEADING", ""),
                postcode=postcode,
                district=district,
                address=a.get("ADDRESS", ""),
                price=_num(a.get("RENT/PER_MONTH_LETTINGS") or a.get("PRICE")),
                size_m2=_num(a.get("ESTATE_SIZE/LIVING_AREA") or a.get("ESTATE_SIZE")),
                rooms=_num(a.get("NUMBER_OF_ROOMS")),
                floor=str(a.get("FLOOR", "")),
                provisionsfrei=(a.get("ISPRIVATE") == "1") if a.get("ISPRIVATE") else None,
                coordinates=coords,
                image_urls=imgs,
                raw={"summary_attrs": a},
            )
        )
    return listings


def _collect_codes(attr_info: list) -> set[str] | None:
    """All attribute codes present on the detail page, or None if there is no
    equipment/attribute info at all (so we can keep elevator/outdoor as unknown)."""
    found: set[str] = set()
    for block in attr_info or []:
        tree = block.get("treeAttributeElement", {})
        found.add(tree.get("code", ""))
        for v in block.get("values", []):
            found.add(v.get("code", ""))
    return found or None


def parse_detail(html: str, base_id: str) -> Listing:
    data = extract_next_data(html) or {}
    ad = data.get("props", {}).get("pageProps", {}).get("advertDetails", {})
    a = _attrs(ad)
    codes = _collect_codes(ad.get("attributeInformation", []))
    if codes is None:
        has_elev = has_out = None
        outdoor = ""
    else:
        has_elev = bool(codes & ELEVATOR_CODES)
        out_hits = codes & OUTDOOR_CODES
        has_out = bool(out_hits)
        outdoor = ", ".join(sorted(out_hits))
    imgs: list[str] = []
    ail = ad.get("advertImageList", {})
    images = ail.get("advertImage", []) if isinstance(ail, dict) else []
    for im in images:
        ref = im.get("mainImageUrl") or im.get("referenceImageUrl") or im.get("selfLink")
        if ref:
            imgs.append(ref if ref.startswith("http") else IMG_BASE + ref)
    return Listing(
        id=base_id,
        source="willhaben",
        url=DETAIL_BASE,
        description=a.get("DESCRIPTION", ""),
        building_condition=a.get("BUILDING_CONDITION", "") or a.get("BUILDING_TYPE", ""),
        available_from=a.get("AVAILABLE_DATE", ""),
        floor=str(a.get("FLOOR", "")),
        has_elevator=has_elev,
        has_outdoor=has_out,
        outdoor=outdoor,
        image_urls=imgs,
        raw={"detail_attrs": a},
    )
