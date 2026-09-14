from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRITERIA_PATH = ROOT / "criteria.toml"

MODES = ("rent", "buy")
# Which [budget] keys each mode reads, in (target, hard cap) order.
_BUDGET_KEYS = {"rent": ("max_rent_kalt", "rent_hard_cap"), "buy": ("max_price", "price_hard_cap")}


@dataclass
class Criteria:
    max_price: int  # target: cold rent/month (rent) or purchase price (buy)
    price_hard_cap: int  # absolute cap; listings above are dropped
    min_size_m2: int
    min_rooms: int
    include_districts: set[int]
    musthave_elevator: bool
    musthave_outdoor: bool
    geocode_contact: str | None = None
    report_language: str = "en"
    mode: str = "rent"
    min_floor: int = 0  # 0 = any; drop only when the floor is explicitly lower
    energy_class: list[str] = field(default_factory=list)  # soft preference, never a filter
    notes: str = ""  # free-text priorities, scored by the skill
    email_to: list[str] = field(default_factory=list)
    email_cc: list[str] = field(default_factory=list)

    # Legacy names (rent mode) used by older code/tests.
    @property
    def max_rent_kalt(self) -> int:
        return self.max_price

    @property
    def rent_hard_cap(self) -> int:
        return self.price_hard_cap


def load_criteria(path: Path = CRITERIA_PATH) -> Criteria:
    if not path.exists():
        raise SystemExit(
            f"{path.name} not found — run /setup in Claude Code to create it "
            f"(or copy criteria.example.toml to {path.name} and edit it)"
        )
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    mode = data.get("search", {}).get("mode", "rent")
    if mode not in MODES:
        raise SystemExit(f"[search].mode = {mode!r} is not one of {MODES}")
    budget = data.get("budget", {})
    target_key, cap_key = _BUDGET_KEYS[mode]
    missing = [k for k in (target_key, cap_key) if k not in budget]
    if missing:
        raise SystemExit(f"[budget] is missing {', '.join(missing)} (required in {mode} mode)")
    musthave = data["musthave"]
    prefs = data.get("preferences", {})
    email = data.get("email", {})
    return Criteria(
        max_price=budget[target_key],
        price_hard_cap=budget[cap_key],
        min_size_m2=data["size"]["min_size_m2"],
        min_rooms=data["size"]["min_rooms"],
        include_districts=set(data["districts"]["include"]),
        musthave_elevator=musthave["elevator"],
        musthave_outdoor=musthave["outdoor"],
        geocode_contact=data.get("geocode", {}).get("contact") or None,
        report_language=data.get("report", {}).get("language", "en"),
        mode=mode,
        min_floor=int(musthave.get("min_floor", 0) or 0),
        energy_class=[str(x).upper() for x in prefs.get("energy_class", [])],
        notes=str(prefs.get("notes", "")).strip(),
        email_to=list(email.get("to", [])),
        email_cc=list(email.get("cc", [])),
    )
