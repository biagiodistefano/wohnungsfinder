"""Buy-mode parsing against saved fixtures. willhaben/derStandard buy fixtures are
optional (their sites 403 plain HTTP); tests skip when the file is absent."""

from pathlib import Path

import pytest

from wohnung.fetch import Fetcher
from wohnung.sources import immoscout as im
from wohnung.sources import immowelt as iw
from wohnung.sources.derstandard_client import DerStandardSource
from wohnung.sources.immoscout_client import ImmoScoutSource
from wohnung.sources.immowelt_client import ImmoweltSource
from wohnung.sources.willhaben_client import WillhabenSource

FIX = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    p = FIX / name
    if not p.exists():
        pytest.skip(f"fixture {name} not captured")
    return p.read_text(encoding="utf-8")


def test_immoscout_buy_keeps_developer_projects():
    listings = im.parse_search(_read("immoscout_buy_search.html"))
    assert len(listings) >= 10
    projects = [l for l in listings if l.is_project]
    assert projects, "developer hits with area ranges must be kept, flagged is_project"
    p = projects[0]
    assert p.price is None  # projects carry no price on the search page
    assert p.size_m2 == 121.0  # upper bound of "74 – 121 m²"
    assert p.rooms == 3.0  # upper bound of "2 – 3 Zimmer"
    assert p.district and 1 <= p.district <= 23
    assert p.url.startswith("https://www.immobilienscout24.at/expose/")


def test_immoscout_detail_sniff_has_expected_keys():
    d = im.sniff_detail(_read("immoscout_buy_detail.html"))
    assert set(d) == {"floor", "energy_class", "hwb", "year_built"}
    assert isinstance(d["floor"], str)


def test_immowelt_buy_cards_carry_price_and_floor():
    listings = iw.parse_search(_read("immowelt_buy_search.html"))
    assert len(listings) >= 20
    l = next(x for x in listings if x.floor)
    assert l.price and l.price > 100000
    assert l.floor[0].isdigit()  # "3" from "3. Geschoss"


def test_buy_urls_and_price_kind():
    f = Fetcher()
    try:
        for cls, key in (
            (WillhabenSource, "eigentumswohnung"),
            (ImmoScoutSource, "wohnung-kaufen"),
            (DerStandardSource, "kaufen-wohnung"),
            (ImmoweltSource, "wohnungen/kaufen"),
        ):
            assert key in cls(f, mode="buy").search_url
            assert "miet" in cls(f).search_url  # rent default unchanged
    finally:
        f.close()


def test_immowelt_search_marks_kauf_and_floor_number():
    html = _read("immowelt_buy_search.html")

    class F:
        def get(self, url, params=None):
            return html

    out = ImmoweltSource(F(), mode="buy").search(max_pages=1)
    assert out and all(l.price_kind == "kauf" for l in out)
    numbered = [l for l in out if l.floor and l.floor[0].isdigit()]
    assert numbered and all(l.floor_number == int(l.floor[0]) for l in numbered if len(l.floor) == 1)


def test_immoscout_search_marks_kauf():
    html = _read("immoscout_buy_search.html")

    class F:
        def get(self, url, params=None):
            if "seite-" in url:
                raise RuntimeError("no page 2 in fixture")
            return html

    out = ImmoScoutSource(F(), mode="buy").search(max_pages=2)
    assert out and all(l.price_kind == "kauf" for l in out)
