"""Best-effort energy certificate sniffing from listing text or embedded JSON.

Returns the HWB class ("A".."G", "" if not found) and the HWB value in kWh/m²a
(None if not found). Never raises; missing data is simply unknown."""

from __future__ import annotations

import re

_CLASS = re.compile(
    r"(?:energieklasse|hwb[-\s]?klasse|\bklasse|finalEnergyDemandClass\W+)\s*[:\"]?\s*([A-G])\+{0,2}\b",
    re.I,
)
_HWB = re.compile(r"(?:hwb|heizwärmebedarf)\D{0,12}?(\d{1,3}(?:[.,]\d)?)\s*kwh", re.I)


def sniff_energy(text: str) -> tuple[str, float | None]:
    if not text:
        return "", None
    cls = ""
    m = _CLASS.search(text)
    if m:
        cls = m.group(1).upper()
    hwb = None
    m = _HWB.search(text)
    if m:
        hwb = float(m.group(1).replace(",", "."))
    return cls, hwb
