from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

TRI = Optional[bool]  # True / False / None (unknown)


@dataclass
class Listing:
    id: str  # source-prefixed stable id, e.g. "willhaben_1701688262"
    source: str
    url: str
    title: str = ""
    district: Optional[int] = None
    postcode: Optional[int] = None
    address: str = ""
    price: Optional[float] = None  # monthly rent (rent mode) or purchase price (buy mode)
    price_kind: str = "unknown"  # "kalt" | "warm" | "kauf" | "unknown"
    price_per_m2: Optional[float] = None  # computed in run_search when price and size exist
    size_m2: Optional[float] = None
    rooms: Optional[float] = None
    floor: str = ""
    floor_number: Optional[int] = None  # parsed from `floor`; None = unknown / Dachgeschoss
    has_elevator: TRI = None
    outdoor: str = ""  # description of outdoor space, "" if none/unknown
    has_outdoor: TRI = None
    provisionsfrei: TRI = None
    building_condition: str = ""
    energy_class: str = ""  # HWB class "A".."G", "" if unknown
    hwb: Optional[float] = None  # kWh/m²a
    is_project: bool = False  # developer/Bauträger project: price is a from-price, size may be None
    available_from: str = ""
    description: str = ""
    coordinates: Optional[tuple[float, float]] = None  # (lat, lng)
    nearest_ubahn: str = ""
    ubahn_distance_m: Optional[int] = None
    image_urls: list[str] = field(default_factory=list)
    local_images: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        d = asdict(self)
        if self.coordinates:
            d["coordinates"] = list(self.coordinates)
        return d
