from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRITERIA_PATH = ROOT / "criteria.toml"


@dataclass
class Criteria:
    max_rent_kalt: int
    rent_hard_cap: int
    min_size_m2: int
    min_rooms: int
    include_districts: set[int]
    musthave_elevator: bool
    musthave_outdoor: bool
    geocode_contact: str | None = None
    report_language: str = "en"


def load_criteria(path: Path = CRITERIA_PATH) -> Criteria:
    if not path.exists():
        raise SystemExit(
            f"{path.name} not found — run /setup in Claude Code to create it "
            f"(or copy criteria.example.toml to {path.name} and edit it)"
        )
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return Criteria(
        max_rent_kalt=data["budget"]["max_rent_kalt"],
        rent_hard_cap=data["budget"]["rent_hard_cap"],
        min_size_m2=data["size"]["min_size_m2"],
        min_rooms=data["size"]["min_rooms"],
        include_districts=set(data["districts"]["include"]),
        musthave_elevator=data["musthave"]["elevator"],
        musthave_outdoor=data["musthave"]["outdoor"],
        geocode_contact=data.get("geocode", {}).get("contact") or None,
        report_language=data.get("report", {}).get("language", "en"),
    )
