"""Durability, wipe-detection, fingerprint persistence, and report-based recovery."""

import json

from wohnung.dedup import fingerprint, fingerprint_from
from wohnung.models import Listing
from wohnung.recover import id_from_url, ids_from_text, reindex
from wohnung.state import State


# --- fingerprint -----------------------------------------------------------

def test_fingerprint_from_matches_listing():
    l = Listing(id="x", source="s", url="u", district=3, rooms=3, size_m2=60.4, price=1549)
    assert fingerprint(l) == fingerprint_from(3, 3, 60.4, 1549) == "3|3|60|1550"


def test_fingerprint_none_when_inputs_missing():
    assert fingerprint_from(None, 3, 60, 1500) is None
    assert fingerprint_from(3, 3, None, 1500) is None
    assert fingerprint_from(3, None, 60, 1500) == "3|?|60|1500"  # rooms optional


# --- atomic writes + backup + wipe detection -------------------------------

def test_record_persists_and_atomic_no_tmp_left(tmp_path):
    p = tmp_path / "seen.json"
    st = State(p)
    assert st.record("willhaben_1", source="willhaben", url="u", status="new")
    assert not st.record("willhaben_1", source="willhaben", url="u")  # idempotent
    assert json.loads(p.read_text())["willhaben_1"]["status"] == "new"
    assert not (tmp_path / "seen.json.tmp").exists()  # temp cleaned up by os.replace


def test_backup_written_and_recovers_from_corruption(tmp_path):
    p = tmp_path / "seen.json"
    st = State(p)
    st.record("a", source="s", url="u", fingerprint="3|3|60|1550")
    # Re-open: the good file is snapshotted to .bak on load.
    State(p)
    assert (tmp_path / "seen.json.bak").exists()
    # Corrupt the main file; next load must recover from backup, not start blank.
    p.write_text("{ this is not valid json")
    st2 = State(p)
    assert not st2.is_new("a")
    assert st2.has_fingerprint("3|3|60|1550")


def test_was_wiped_detects_emptied_state(tmp_path):
    p = tmp_path / "seen.json"
    st = State(p)
    st.record("a", source="s", url="u")
    State(p)  # creates the .bak snapshot
    # Simulate a wipe: empty the main file but leave the backup.
    p.write_text("{}")
    wiped = State(p)
    assert wiped.was_wiped()
    assert wiped.count_loaded == 0


def test_not_wiped_on_genuine_first_run(tmp_path):
    st = State(tmp_path / "seen.json")  # nothing on disk, no backup
    assert not st.was_wiped()


def test_meta_rebuilds_fingerprint_when_field_absent(tmp_path):
    p = tmp_path / "seen.json"
    State(p).record("a", source="s", url="u", meta={"district": 3, "rooms": 3, "size_m2": 60, "rent": 1549})
    # Stored meta but no explicit fingerprint field — it must be recomputed on load.
    assert "fingerprint" not in json.loads(p.read_text())["a"]
    assert State(p).has_fingerprint("3|3|60|1550")


# --- URL -> id mapping -----------------------------------------------------

def test_id_from_url_per_source():
    assert id_from_url(
        "https://www.willhaben.at/iad/immobilien/d/mietwohnungen/wien/wien-1050-margareten/helle-3-zimmerwohnung-mit-loggia-800890941/"
    ) == "willhaben_800890941"
    assert id_from_url("https://www.immobilienscout24.at/expose/692d4e8702be9d88330023c8") == "immoscout_692d4e8702be9d88330023c8"
    assert id_from_url("https://www.immowelt.at/expose/cc19f015-366a-4403-85e4-92d7e5ca25b0") == "immowelt_cc19f015-366a-4403-85e4-92d7e5ca25b0"
    assert id_from_url("https://immobilien.derstandard.at/detail/15166553") == "derstandard_15166553"
    assert id_from_url("https://example.com/whatever") is None


def test_ids_from_text_handles_anchors_and_trailing_punct():
    text = '<a href="https://immobilien.derstandard.at/detail/15166553" target="_blank">link</a> ' \
           "and bare https://www.immobilienscout24.at/expose/abc123def456)."
    ids = ids_from_text(text)
    assert ids["derstandard_15166553"].endswith("/15166553")
    assert "immoscout_abc123def456" in ids  # trailing ")." stripped


# --- reindex (recover lost state from reports) -----------------------------

def test_reindex_rebuilds_state_from_reports(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "reports" / "2026-06-08-1920.md").write_text(
        'see <a href="https://immobilien.derstandard.at/detail/15166553">x</a> and '
        '<a href="https://www.willhaben.at/iad/immobilien/d/mietwohnungen/wien/wien-1050-margareten/helle-800890941/">y</a>'
    )
    (tmp_path / "reports" / ".last_run.json").write_text(json.dumps({
        "new_listings": [{"id": "willhaben_800890941", "url": "u", "district": 5, "rooms": 3, "size_m2": 73, "price": 1395}],
        "excluded": [], "duplicates": [],
    }))
    r = reindex(tmp_path)
    assert r["added"] == 2
    st = State(tmp_path / "state" / "seen.json")
    assert not st.is_new("derstandard_15166553")
    assert not st.is_new("willhaben_800890941")
    # richer .last_run.json record carried fingerprint inputs
    assert st.has_fingerprint("5|3|73|1400")


def test_reindex_is_non_destructive(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "state").mkdir()
    st = State(tmp_path / "state" / "seen.json")
    st.record("willhaben_800890941", source="willhaben", url="u", status="interested")
    (tmp_path / "reports" / "r.md").write_text(
        '<a href="https://www.willhaben.at/iad/immobilien/d/mietwohnungen/wien/x-800890941/">y</a>'
    )
    reindex(tmp_path)
    # existing status preserved, not reset to "seen"
    assert State(tmp_path / "state" / "seen.json").get("willhaben_800890941")["status"] == "interested"


def test_state_recomputes_fingerprint_from_legacy_rent_meta(tmp_path):
    p = tmp_path / "seen.json"
    State(p).record("a", source="s", url="u", meta={"district": 3, "rooms": 3, "size_m2": 60, "rent": 1549})
    st = State(p)
    assert st.has_fingerprint(fingerprint_from(3, 3, 60, 1549))
