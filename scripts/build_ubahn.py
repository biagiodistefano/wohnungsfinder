"""Build wohnung/data/ubahn_stations.json from Wiener Linien open data.

The OGD `steige` export currently lacks the column that links platform StopIDs to
the coordinates in `haltestellen`, so we can't follow line->stop->coords directly.
Instead we match the `haltestellen` rows (which DO have accurate coordinates) against
the known set of Vienna U-Bahn station names. Names are stable; coords come straight
from the official file. Run once and commit the JSON so searches stay offline.

Usage: uv run python scripts/build_ubahn.py
"""

from __future__ import annotations

import csv
import io
import json
import unicodedata
from pathlib import Path

import httpx

HALTESTELLEN = "https://www.wienerlinien.at/ogd_realtime/doku/ogd/wienerlinien-ogd-haltestellen.csv"

# Canonical Vienna U-Bahn station names (U1, U2, U3, U4, U6), deduped across lines.
UBAHN_STATIONS = [
    # U1
    "Oberlaa", "Neulaa", "Alaudagasse", "Altes Landgut", "Troststraße", "Reumannplatz",
    "Keplerplatz", "Südtiroler Platz-Hauptbahnhof", "Taubstummengasse", "Karlsplatz",
    "Stephansplatz", "Schwedenplatz", "Nestroyplatz", "Praterstern", "Vorgartenstraße",
    "Donauinsel", "Kaisermühlen-VIC", "Alte Donau", "Kagran", "Kagraner Platz",
    "Rennbahnweg", "Aderklaaer Straße", "Großfeldsiedlung", "Leopoldau",
    # U2
    "Museumsquartier", "Volkstheater", "Rathaus", "Schottentor", "Schottenring",
    "Taborstraße", "Messe-Prater", "Krieau", "Stadion", "Donaumarina", "Donaustadtbrücke",
    "Stadlau", "Hardeggasse", "Donauspital", "Aspern Nord", "Hausfeldstraße",
    "Aspernstraße", "Seestadt",
    # U3
    "Ottakring", "Kendlerstraße", "Hütteldorfer Straße", "Johnstraße", "Schweglerstraße",
    "Westbahnhof", "Zieglergasse", "Neubaugasse", "Herrengasse", "Stubentor", "Landstraße",
    "Rochusgasse", "Kardinal-Nagl-Platz", "Schlachthausgasse", "Erdberg", "Gasometer",
    "Zippererstraße", "Enkplatz", "Simmering",
    # U4
    "Hütteldorf", "Ober St. Veit", "Unter St. Veit", "Braunschweiggasse", "Hietzing",
    "Schönbrunn", "Meidling Hauptstraße", "Längenfeldgasse", "Margaretengürtel",
    "Pilgramgasse", "Kettenbrückengasse", "Stadtpark", "Roßauer Lände", "Friedensbrücke",
    "Spittelau", "Heiligenstadt",
    # U6
    "Siebenhirten", "Perfektastraße", "Erlaaer Straße", "Alterlaa", "Am Schöpfwerk",
    "Tscherttegasse", "Bahnhof Meidling", "Niederhofstraße", "Gumpendorfer Straße",
    "Burggasse-Stadthalle", "Thaliastraße", "Josefstädter Straße", "Alser Straße",
    "Michelbeuern-AKH", "Währinger Straße-Volksoper", "Nußdorfer Straße", "Jägerstraße",
    "Dresdner Straße", "Handelskai", "Neue Donau", "Floridsdorf",
]


# Canonical name -> the name as it appears in the Wiener Linien haltestellen file.
ALIASES = {
    "Südtiroler Platz-Hauptbahnhof": "Hauptbahnhof",
    "Landstraße": "Mitte-Landstraße",
    "Hütteldorf": "Bhf. Hütteldorf",
    "Bahnhof Meidling": "Bhf. Meidling",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    for ch in " -.,/":
        s = s.replace(ch, "")
    return s


def main():
    txt = httpx.get(HALTESTELLEN, timeout=30).text.replace("\r", "")
    rows = list(csv.DictReader(io.StringIO(txt), delimiter=";"))
    # index haltestellen by normalized name -> (lat, lng), averaging duplicates
    by_name: dict[str, list[tuple[float, float]]] = {}
    for r in rows:
        name = r.get("PlatformText") or ""
        lat, lng = r.get("Latitude"), r.get("Longitude")
        if name and lat and lng:
            try:
                by_name.setdefault(norm(name), []).append((float(lat), float(lng)))
            except ValueError:
                pass

    out, unmatched = [], []
    for station in UBAHN_STATIONS:
        coords = by_name.get(norm(ALIASES.get(station, station)))
        if not coords:
            unmatched.append(station)
            continue
        lat = sum(c[0] for c in coords) / len(coords)
        lng = sum(c[1] for c in coords) / len(coords)
        out.append({"name": station, "lat": round(lat, 6), "lng": round(lng, 6)})

    p = Path(__file__).resolve().parent.parent / "wohnung" / "data" / "ubahn_stations.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(out)} stations to {p}")
    if unmatched:
        print(f"UNMATCHED ({len(unmatched)}): {unmatched}")


if __name__ == "__main__":
    main()
