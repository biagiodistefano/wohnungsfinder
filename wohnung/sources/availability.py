"""Best-effort move-in availability sniffer for sources without a structured field.

Willhaben exposes a clean AVAILABLE_DATE attribute; ImmoScout24 and derStandard don't,
so we read the detail-page text. Conservative on purpose: prefer an explicit
"verfügbar/bezug/frei ab <date>" construction, fall back to "ab sofort". Returns "" when
nothing reliable is found — the skill treats the value as a hint, not gospel.
"""

from __future__ import annotations

import re

_DATE = re.compile(
    r"(?:verfügbar|bezugsfrei|beziehbar|bezug|frei)\s*(?:ab|per)?\s*:?\s*(\d{1,2}\.\d{1,2}\.\d{4})",
    re.I,
)
_MONTH = re.compile(
    r"(?:verfügbar|bezugsfrei|beziehbar|bezug|frei)\s*ab\s*"
    r"((?:jänner|januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{4})",
    re.I,
)
_SOFORT = re.compile(r"ab\s+sofort|sofort\s+(?:beziehbar|verfügbar|bezugsfrei|bezug)", re.I)


def sniff_available(text: str) -> str:
    if not text:
        return ""
    m = _DATE.search(text) or _MONTH.search(text)
    if m:
        return m.group(1)
    if _SOFORT.search(text):
        return "sofort"
    return ""
