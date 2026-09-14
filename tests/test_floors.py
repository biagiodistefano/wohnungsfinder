import pytest

from wohnung.floors import parse_floor


@pytest.mark.parametrize("s,expected", [
    ("3", 3), ("3. Stock", 3), ("3. OG", 3), ("3.OG", 3), ("3. Geschoss", 3), ("3. Etage", 3),
    ("12", 12), ("1. Stock mit Lift", 1),
    ("EG", 0), ("Erdgeschoss", 0), ("Parterre", 0), ("Hochparterre", 0), ("HP", 0),
    ("DG", None), ("Dachgeschoss", None), ("", None), ("Souterrain", None), ("Maisonette", None),
])
def test_parse_floor(s, expected):
    assert parse_floor(s) == expected
