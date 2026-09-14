from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from wohnung.dedup import fingerprint_from, meta_price


class State:
    """Persistent set of seen listing ids (state/seen.json), with a status per id.

    Durability: every write is atomic (temp file + ``os.replace``) so a crash can never
    truncate or corrupt the file mid-write. On load, the good (non-empty) state is
    snapshotted to ``seen.json.bak``; if the main file is later deleted or emptied,
    :meth:`was_wiped` reports it and the backup is the recovery source (``wohnung
    reindex`` can also rebuild from past reports). Losing this state silently makes every
    listing look new again — which is exactly the failure we guard against here.
    """

    def __init__(self, path: Path, mode: str = "rent"):
        self.path = Path(path)
        self.mode = mode  # search mode: sets the price rounding of the dedup fingerprint
        self.bak_path = self.path.with_name(self.path.name + ".bak")
        self._data: dict[str, dict] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                # Corrupt/truncated main file — recover from the last good backup rather
                # than silently starting blank (which would re-surface every listing).
                self._data = self._load_bak()
        self.count_loaded = len(self._data)
        # Snapshot the good state we just loaded so the next run can recover from an
        # accidental wipe. Only when non-empty: never overwrite a real backup with "".
        if self._data and self.path.exists():
            self._write_bak()
        self._fingerprints = self._collect_fingerprints()

    # --- loading helpers -------------------------------------------------

    def _load_bak(self) -> dict:
        if self.bak_path.exists():
            try:
                return json.loads(self.bak_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                return {}
        return {}

    def _backup_count(self) -> int:
        return len(self._load_bak())

    def was_wiped(self) -> bool:
        """True if state loaded empty but a non-empty backup exists — i.e. seen.json was
        lost or emptied since the last run, so every listing will look 'new'."""
        return self.count_loaded == 0 and self._backup_count() > 0

    def _collect_fingerprints(self) -> set[str]:
        """Set of cross-source dedup keys from stored records. Uses the saved
        ``fingerprint`` when present, else recomputes it from the saved ``meta`` inputs
        (so records written before the fingerprint field, or after a formula change,
        still participate in dedup once meta is available)."""
        fps: set[str] = set()
        for v in self._data.values():
            fp = v.get("fingerprint")
            if not fp:
                m = v.get("meta")
                if m:
                    fp = fingerprint_from(
                        m.get("district"), m.get("rooms"), m.get("size_m2"), meta_price(m),
                        mode=self.mode,
                    )
            if fp:
                fps.add(fp)
        return fps

    # --- queries ---------------------------------------------------------

    def is_new(self, listing_id: str) -> bool:
        return listing_id not in self._data

    def filter_new(self, ids: list[str]) -> list[str]:
        return [i for i in ids if self.is_new(i)]

    def has_fingerprint(self, fp: str | None) -> bool:
        """True if a listing with this fingerprint was already seen (any source/run)."""
        return bool(fp) and fp in self._fingerprints

    def get(self, listing_id: str) -> dict | None:
        return self._data.get(listing_id)

    def __len__(self) -> int:
        return len(self._data)

    # --- mutations -------------------------------------------------------

    def record(
        self, listing_id: str, *, source: str, url: str, status: str = "new",
        fingerprint: str | None = None, meta: dict | None = None,
    ) -> bool:
        """Record a listing id. Returns True if newly added, False if already known.

        ``meta`` should carry the fingerprint inputs (district/rooms/size_m2/rent) so the
        dedup key can be recomputed later even without the live Listing."""
        if listing_id in self._data:
            return False
        rec: dict = {"source": source, "url": url, "status": status}
        if fingerprint:
            rec["fingerprint"] = fingerprint
            self._fingerprints.add(fingerprint)
        if meta:
            rec["meta"] = {k: v for k, v in meta.items() if v is not None}
        self._data[listing_id] = rec
        self._save()
        return True

    def mark(self, listing_id: str, status: str):
        if listing_id in self._data:
            self._data[listing_id]["status"] = status
            self._save()

    # --- persistence -----------------------------------------------------

    def _write_bak(self):
        try:
            shutil.copy2(self.path, self.bak_path)
        except OSError:
            pass  # backup is best-effort; never let it break a run

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, self.path)  # atomic: readers never see a half-written file
