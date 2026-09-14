from pathlib import Path

from wohnung.sources.derstandard import parse_search as ds_parse
from wohnung.sources.immoscout import parse_search as im_parse

FIX = Path(__file__).parent / "fixtures"


def test_immoscout_parses_real_listings():
    listings = im_parse((FIX / "immoscout_search.html").read_text(encoding="utf-8"))
    assert listings
    l = listings[0]
    assert l.id.startswith("immoscout_")
    assert l.price and l.price > 0
    assert l.size_m2 and l.size_m2 > 0
    assert l.district and 1 <= l.district <= 23
    assert l.url.startswith("https://www.immobilienscout24.at/expose/")


def test_derstandard_parses_real_cards():
    listings = ds_parse((FIX / "derstandard_search.html").read_text(encoding="utf-8"))
    assert listings
    l = listings[0]
    assert l.id.startswith("derstandard_")
    assert l.title
    assert l.price and l.price > 0
    assert l.size_m2 and l.size_m2 > 0
    assert l.rooms and l.rooms > 0
    # district comes from enrich() (detail page), not the search cards
    assert len(listings) >= 5
