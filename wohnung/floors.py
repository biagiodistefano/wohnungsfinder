"""Turn a portal's free-form floor string into a number.

Ground level (EG, Erdgeschoss, Parterre, Hochparterre) is 0. Dachgeschoss and anything
we can't read return None so the must-have filter keeps the listing (unknown ≠ too low)
and the skill still sees the original string."""

from __future__ import annotations

import re

_GROUND = re.compile(r"^\s*(eg|hp|erdgeschoss|parterre|hochparterre)\b", re.I)
_NUM = re.compile(r"^\s*(\d{1,2})\s*(?:\.|\b)")


def parse_floor(s: str) -> int | None:
    if not s:
        return None
    if _GROUND.match(s):
        return 0
    m = _NUM.match(s)
    if m:
        return int(m.group(1))
    return None
