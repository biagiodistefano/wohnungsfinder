from pathlib import Path

from wohnung.dedup import fingerprint
from wohnung.models import Listing
from wohnung.sources.immowelt import parse_search

FIX = Path(__file__).parent / "fixtures"


def test_immowelt_parses_card_titles():
    listings = parse_search((FIX / "immowelt_search.html").read_text(encoding="utf-8"))
    assert len(listings) >= 10
    l = listings[0]
    assert l.id.startswith("immowelt_")
    assert l.url.startswith("https://www.immowelt.at/expose/")
    assert l.rent and l.rent > 0
    assert l.size_m2 and l.size_m2 > 0
    assert l.rooms and l.rooms > 0


def test_fingerprint_matches_crosspost_and_skips_incomplete():
    a = Listing(id="willhaben_1", source="willhaben", url="u", district=7, rooms=3, size_m2=70.4, rent=1198)
    b = Listing(id="immowelt_2", source="immowelt", url="u", district=7, rooms=3, size_m2=70, rent=1200)
    assert fingerprint(a) == fingerprint(b)  # same flat, different portals -> merge
    assert fingerprint(Listing(id="x", source="s", url="u", district=None)) is None  # incomplete -> no merge
