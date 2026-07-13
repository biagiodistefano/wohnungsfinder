from pathlib import Path

import pytest

from wohnung.config import ROOT, load_criteria

EXAMPLE = ROOT / "criteria.example.toml"


def test_load_criteria_example_template():
    # criteria.toml is personal and gitignored; tests run against the committed template.
    c = load_criteria(EXAMPLE)
    assert c.max_rent_kalt == 1500
    assert c.rent_hard_cap == 1650
    assert c.min_size_m2 == 70
    assert c.min_rooms == 3
    assert 1 in c.include_districts and 23 in c.include_districts
    assert 20 not in c.include_districts and 22 not in c.include_districts
    assert c.musthave_elevator and c.musthave_outdoor
    assert c.report_language == "en"
    assert c.geocode_contact is None  # empty string in the template -> None


def test_missing_criteria_points_to_setup(tmp_path: Path):
    with pytest.raises(SystemExit, match="/setup"):
        load_criteria(tmp_path / "criteria.toml")
