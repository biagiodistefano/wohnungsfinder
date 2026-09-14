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
