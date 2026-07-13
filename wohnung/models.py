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
    rent: Optional[float] = None  # headline monthly rent (may be kalt or warm; flagged)
    rent_kind: str = "unknown"  # "kalt" | "warm" | "unknown"
    size_m2: Optional[float] = None
    rooms: Optional[float] = None
    floor: str = ""
    has_elevator: TRI = None
    outdoor: str = ""  # description of outdoor space, "" if none/unknown
    has_outdoor: TRI = None
    provisionsfrei: TRI = None
    building_condition: str = ""
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
