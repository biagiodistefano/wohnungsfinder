"""Light smoke coverage for the core non-network pieces."""

from wohnung.config import Criteria
from wohnung.filters import hard_filter
from wohnung.models import Listing
from wohnung.state import State
from wohnung.ubahn import haversine_m, nearest_ubahn

C = Criteria(1500, 1650, 60, 3, set(range(1, 20)) | {23}, True, True)


def _listing(**kw):
    d = dict(district=7, price=1200, size_m2=70, rooms=3, has_elevator=True, has_outdoor=True)
    d.update(kw)
    return Listing(id="x", source="s", url="u", **d)


def test_hard_filter_keep_and_drops():
    assert hard_filter(_listing(), C)[0]
    assert not hard_filter(_listing(district=21), C)[0]
    assert not hard_filter(_listing(price=1700), C)[0]
    assert not hard_filter(_listing(size_m2=50), C)[0]
    assert not hard_filter(_listing(rooms=2), C)[0]
    assert not hard_filter(_listing(has_elevator=False), C)[0]
    assert not hard_filter(_listing(has_outdoor=False), C)[0]
    # unknown (None) must be kept
    assert hard_filter(_listing(has_elevator=None, has_outdoor=None), C)[0]


def test_state_dedup_and_status(tmp_path):
    st = State(tmp_path / "seen.json")
    assert st.is_new("a")
    st.record("a", source="s", url="u")
    assert not st.is_new("a")
    assert st.filter_new(["a", "b"]) == ["b"]
    st.mark("a", "interested")
    assert State(tmp_path / "seen.json").get("a")["status"] == "interested"


def test_ubahn_nearest():
    assert 600 < haversine_m(48.2007, 16.3690, 48.2083, 16.3725) < 1300
    name, dist = nearest_ubahn(48.2083, 16.3725)  # near Stephansplatz
    assert name and dist >= 0


from wohnung.dedup import fingerprint_from  # noqa: E402

BUY = Criteria(450000, 500000, 70, 3, set(range(1, 10)), False, True, mode="buy", min_floor=3)


def _buy(**kw):
    d = dict(district=4, price=480000, size_m2=80, rooms=3, has_outdoor=True, floor_number=4)
    d.update(kw)
    return Listing(id="b", source="s", url="u", **d)


def test_hard_filter_buy_price_cap_and_floor():
    assert hard_filter(_buy(), BUY)[0]
    assert hard_filter(_buy(price=500000), BUY)[0]  # at cap: keep
    assert not hard_filter(_buy(price=500001), BUY)[0]
    assert not hard_filter(_buy(floor_number=2), BUY)[0]  # explicitly lower: drop
    assert hard_filter(_buy(floor_number=None, floor="DG"), BUY)[0]  # unknown/DG: keep
    assert hard_filter(_buy(floor_number=0, price=1200), C)[0]  # min_floor=0 -> no floor filter
    assert hard_filter(_buy(size_m2=None), BUY)[0]  # project without size: keep


def test_fingerprint_rounding_per_mode():
    assert fingerprint_from(4, 3, 80, 479500, mode="buy") == fingerprint_from(4, 3, 80, 480400, mode="buy")
    assert fingerprint_from(4, 3, 80, 479500, mode="buy") != fingerprint_from(4, 3, 80, 481000, mode="buy")
    assert fingerprint_from(7, 3, 70, 1198) == fingerprint_from(7, 3, 70, 1202)  # rent default: 10
    assert fingerprint_from(7, 3, 70, 1198) != fingerprint_from(7, 3, 70, 1215)


def test_state_uses_mode_for_fingerprints(tmp_path):
    p = tmp_path / "seen.json"
    State(p, mode="buy").record(
        "a", source="s", url="u", meta={"district": 4, "rooms": 3, "size_m2": 80, "price": 479500}
    )
    assert State(p, mode="buy").has_fingerprint(fingerprint_from(4, 3, 80, 480400, mode="buy"))
    assert not State(p, mode="rent").has_fingerprint(fingerprint_from(4, 3, 80, 480400, mode="buy"))


from wohnung.cli import price_per_m2  # noqa: E402


def test_price_per_m2():
    assert price_per_m2(_buy(price=480000, size_m2=80)) == 6000
    assert price_per_m2(_buy(size_m2=None)) is None
    assert price_per_m2(_buy(price=None)) is None
