from pathlib import Path

import pytest

from wohnung.config import ROOT, load_criteria

EXAMPLE = ROOT / "criteria.example.toml"

RENT_MIN = """
[budget]
max_rent_kalt = 1500
rent_hard_cap = 1650
[size]
min_size_m2 = 70
min_rooms = 3
[districts]
include = [1, 2]
[musthave]
elevator = true
outdoor = true
"""

BUY = """
[search]
mode = "buy"
[report]
language = "de"
[budget]
max_price = 450000
price_hard_cap = 500000
[size]
min_size_m2 = 70
min_rooms = 3
[districts]
include = [1, 2, 3, 4, 5, 6, 7, 8, 9]
[musthave]
elevator = false
outdoor = true
min_floor = 3
[preferences]
energy_class = ["A", "b"]
notes = \"\"\"
combined kitchen and living room
\"\"\"
[email]
to = ["friend@example.com"]
cc = ["me@example.com"]
"""


def test_load_criteria_example_template():
    # criteria.toml is personal and gitignored; tests run against the committed template.
    c = load_criteria(EXAMPLE)
    assert c.mode == "rent"
    assert c.max_price == 1500 and c.price_hard_cap == 1650
    assert c.max_rent_kalt == 1500 and c.rent_hard_cap == 1650  # legacy aliases
    assert c.min_size_m2 == 70 and c.min_rooms == 3
    assert 1 in c.include_districts and 23 in c.include_districts
    assert 20 not in c.include_districts and 22 not in c.include_districts
    assert c.musthave_elevator and c.musthave_outdoor
    assert c.min_floor == 0
    assert c.energy_class == []
    assert c.notes == ""
    assert c.email_to == [] and c.email_cc == []
    assert c.report_language == "en"
    assert c.geocode_contact is None  # empty string in the template -> None


def test_rent_profile_without_search_section_defaults_to_rent(tmp_path: Path):
    p = tmp_path / "criteria.toml"
    p.write_text(RENT_MIN, encoding="utf-8")
    c = load_criteria(p)
    assert c.mode == "rent" and c.price_hard_cap == 1650


def test_buy_profile(tmp_path: Path):
    p = tmp_path / "criteria.toml"
    p.write_text(BUY, encoding="utf-8")
    c = load_criteria(p)
    assert c.mode == "buy"
    assert c.max_price == 450000 and c.price_hard_cap == 500000
    assert c.min_floor == 3
    assert c.energy_class == ["A", "B"]  # upper-cased
    assert "kitchen" in c.notes
    assert c.email_to == ["friend@example.com"] and c.email_cc == ["me@example.com"]
    assert c.report_language == "de"


def test_buy_profile_missing_budget_keys_names_them(tmp_path: Path):
    p = tmp_path / "criteria.toml"
    p.write_text(BUY.replace("max_price = 450000\nprice_hard_cap = 500000\n", ""), encoding="utf-8")
    with pytest.raises(SystemExit, match="max_price"):
        load_criteria(p)


def test_unknown_mode_rejected(tmp_path: Path):
    p = tmp_path / "criteria.toml"
    p.write_text(BUY.replace('mode = "buy"', 'mode = "lease"'), encoding="utf-8")
    with pytest.raises(SystemExit, match="lease"):
        load_criteria(p)


def test_missing_criteria_points_to_setup(tmp_path: Path):
    with pytest.raises(SystemExit, match="/setup"):
        load_criteria(tmp_path / "criteria.toml")
