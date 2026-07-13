from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "ubahn_stations.json"


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def _stations() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def nearest_ubahn(lat: float, lng: float) -> tuple[str, int]:
    best_name, best_d = "", float("inf")
    for s in _stations():
        d = haversine_m(lat, lng, s["lat"], s["lng"])
        if d < best_d:
            best_name, best_d = s["name"], d
    return best_name, int(round(best_d))
