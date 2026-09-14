# Buy Mode + Email Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Vienna apartment tool search for apartments to buy (Eigentumswohnung) as well as to rent, selected by a `mode` key in `criteria.toml`, and email each report via SMTP at the end of a run.

**Architecture:** A `[search].mode` switch flows from `criteria.toml` through `Criteria` into `build_sources(fetcher, mode)`, the dedup fingerprint, and the Claude skill's rubric. The `Listing.rent` field is generalized to `price` (+ `price_kind`), and buy-specific data (floor number, energy class, developer-project flag, €/m²) is added. The mailer is restored from history commit `3dad2cd` of the backup bundle (`~/wohnungfinder-history-backup.bundle`) and generalized.

**Tech Stack:** Python ≥ 3.12, `httpx`, `python-dotenv`, `smtplib` (stdlib), `pytest` with saved HTML fixtures (offline). `uv` for everything (`uv run pytest`, `uv add`).

**Spec:** `docs/superpowers/specs/2026-09-14-buy-mode-and-email-design.md`

## Global Constraints

- Never commit `criteria.toml`, `.env`, `reports/`, `state/`, `images/`, `logs/`, `*.pdf`. Only `criteria.example.toml` and `.env.example` are committed.
- Never push. Commit locally only (the remote still has old personal history; see memory).
- Tests must run offline against fixtures under `tests/fixtures/`. No network in tests.
- Rent mode must keep working with a `criteria.toml` that has no `[search]` section (default mode = `"rent"`).
- Elevator / outdoor / floor must-haves drop a listing **only when explicitly absent or explicitly below**; unknown (`None`) is kept.
- Energy class is **never** a hard filter.
- Module for email is named `mailer` (not `email`) so it does not shadow the stdlib `email` package.
- Each task: write the failing test, watch it fail, implement, watch it pass, commit with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` as the last line of the message.
- Captured live pages for fixtures are in the scratchpad: `/private/tmp/claude-501/-Users-biagio-repos-personal-wohnungfinder/ae0e8b58-da63-45a8-ad46-1480aeb1beef/scratchpad/{immoscout_buy.html,immoscout_buy_detail.html,immowelt_buy.html}`. willhaben and derStandard buy pages could not be fetched (403); their buy tests are skipped if the fixture file is absent.

---

## File map

| File | Responsibility | Action |
|---|---|---|
| `wohnung/mailer.py` | SMTP send + `.env` loading | create (restore) |
| `.env.example` | documented SMTP variables | create (restore) |
| `.gitignore` | ignore `.env` | modify |
| `pyproject.toml` | add `python-dotenv` | modify |
| `wohnung/cli.py` | `email` subcommand; pass mode to sources; €/m²; `mode` in `.last_run.json` | modify |
| `wohnung/config.py` | `mode`, generalized price caps, `min_floor`, `energy_class`, `notes`, `email_to/cc` | modify |
| `criteria.example.toml` | document every new key | modify |
| `wohnung/models.py` | `rent`→`price`, `price_kind`, `price_per_m2`, `floor_number`, `energy_class`, `hwb`, `is_project` | modify |
| `wohnung/floors.py` | `parse_floor(str) -> int \| None` | create |
| `wohnung/energy.py` | `sniff_energy(text) -> (class, hwb)` | create |
| `wohnung/filters.py` | price cap + `min_floor` | modify |
| `wohnung/dedup.py` | mode-aware price rounding | modify |
| `wohnung/state.py` | mode-aware recompute; legacy `rent` meta | modify |
| `wohnung/recover.py` | legacy `rent` meta | modify |
| `wohnung/sources/*_client.py` | rent/buy URLs, `mode` ctor arg, `price_kind`, energy/floor enrich | modify |
| `wohnung/sources/immoscout.py` | keep developer-project hits (`is_project`) | modify |
| `wohnung/sources/willhaben.py` | energy class from attributes | modify |
| `tests/test_mailer.py` | message assembly with fake SMTP | create |
| `tests/test_config.py`, `tests/test_core.py`, `tests/test_floors.py`, `tests/test_energy.py`, `tests/test_buy_sources.py` | new coverage | create/modify |
| `tests/fixtures/immoscout_buy_search.html`, `immoscout_buy_detail.html`, `immowelt_buy_search.html` | buy fixtures | create (copy) |
| `.claude/skills/wohnung-search/SKILL.md` | buy rubric, email step | modify |
| `.claude/skills/setup/SKILL.md` | mode/floor/energy/notes/email questions | modify |
| `.claude/commands/wohnung-search.md` | wording | modify |
| `README.md` | buy mode, email, privacy table | modify |

---

### Task 1: Restore the SMTP mailer

**Files:**
- Create: `wohnung/mailer.py`, `.env.example`, `tests/test_mailer.py`
- Modify: `.gitignore`, `pyproject.toml`, `wohnung/cli.py` (the `main()` argparser, after the `pdf` subparser)

**Interfaces:**
- Produces: `mailer.send_report(path, to: list[str], cc: list[str] | None = None, subject: str | None = None, body_text: str | None = None) -> list[str]`; `mailer.verify_login() -> str`; `mailer.build_message(path, to, cc, subject, body_text) -> EmailMessage` (pure, testable); CLI `uv run wohnung email <report.md|.pdf> [--to X] [--cc Y] [--verify]`.
- Recipients come from `criteria.toml [email] to/cc` (read via `tomllib` directly in the CLI for now; Task 2 moves them onto `Criteria`).

- [ ] **Step 1: Add the dependency and ignore rules**

```bash
cd /Users/biagio/repos/personal/wohnungfinder
uv add "python-dotenv>=1.0"
```

Append to `.gitignore` under the "Personal / local-only" block:

```
.env
.env.*
!.env.example
```

- [ ] **Step 2: Write the failing test**

`tests/test_mailer.py`:

```python
"""Mailer: message assembly only. Never touches the network."""

from pathlib import Path

import pytest

from wohnung import mailer


def _report(tmp_path: Path) -> Path:
    md = tmp_path / "2026-09-14-0900.md"
    md.write_text(
        "# Report\n\nTop pick: <a href=\"https://example.com/x\">link</a>\n\n- item one\n",
        encoding="utf-8",
    )
    return md


def test_build_message_from_markdown_has_html_and_text(tmp_path):
    md = _report(tmp_path)
    msg = mailer.build_message(md, to=["a@example.com"], cc=["b@example.com"], sender="me@example.com")
    assert msg["To"] == "a@example.com"
    assert msg["Cc"] == "b@example.com"
    assert msg["From"] == "me@example.com"
    assert "2026-09-14-0900" in msg["Subject"]
    body = msg.get_body(preferencelist=("html",))
    assert body is not None
    assert "https://example.com/x" in body.get_content()
    assert msg.get_body(preferencelist=("plain",)) is not None
    assert not list(msg.iter_attachments())  # no sibling .pdf -> no attachment


def test_build_message_attaches_sibling_pdf(tmp_path):
    md = _report(tmp_path)
    md.with_suffix(".pdf").write_bytes(b"%PDF-1.4 fake")
    msg = mailer.build_message(md, to=["a@example.com"], cc=None, sender="me@example.com")
    atts = list(msg.iter_attachments())
    assert len(atts) == 1
    assert atts[0].get_filename() == "2026-09-14-0900.pdf"
    assert atts[0].get_content_type() == "application/pdf"


def test_build_message_from_pdf_path_attaches_it(tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    msg = mailer.build_message(pdf, to=["a@example.com"], cc=None, sender="me@example.com")
    assert [a.get_filename() for a in msg.iter_attachments()] == ["r.pdf"]


def test_send_report_requires_env(tmp_path, monkeypatch):
    for k in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(mailer, "load_env", lambda: None)  # don't read a real .env
    with pytest.raises(RuntimeError, match="EMAIL_HOST"):
        mailer.send_report(_report(tmp_path), to=["a@example.com"])


def test_send_report_uses_smtp(tmp_path, monkeypatch):
    monkeypatch.setattr(mailer, "load_env", lambda: None)
    monkeypatch.setenv("EMAIL_HOST", "smtp.example.com")
    monkeypatch.setenv("EMAIL_HOST_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_HOST_PASSWORD", "pw")
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port):
            sent["host"], sent["port"] = host, port
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self, context=None): sent["tls"] = True
        def login(self, u, p): sent["login"] = (u, p)
        def send_message(self, msg, to_addrs=None): sent["to_addrs"] = to_addrs

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    rcpts = mailer.send_report(_report(tmp_path), to=["a@example.com"], cc=["b@example.com"])
    assert rcpts == ["a@example.com", "b@example.com"]
    assert sent == {"host": "smtp.example.com", "port": 587, "tls": True,
                    "login": ("me@example.com", "pw"), "to_addrs": rcpts}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_mailer.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'wohnung.mailer'`

- [ ] **Step 4: Write the mailer**

`wohnung/mailer.py`:

```python
"""Email a report via SMTP. Credentials come from the environment (loaded from .env at
the repo root), recipients from criteria.toml's [email] section. Named `mailer` (not
`email`) so it does not shadow the stdlib `email` package that smtplib depends on."""

from __future__ import annotations

import html
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def load_env() -> None:
    """Load .env from the repo root into the environment (no-op if absent)."""
    load_dotenv(ROOT / ".env")


def markdown_to_html(md: str) -> str:
    """Minimal, dependency-free markdown -> HTML good enough for an email body:
    headings, bullet lists, paragraphs, **bold**, and pass-through of existing <a> tags."""
    out: list[str] = []
    in_list = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        # protect existing anchors, escape the rest
        parts = re.split(r"(<a\s[^>]*>.*?</a>)", line, flags=re.I | re.S)
        esc = "".join(p if re.match(r"<a\s", p, re.I) else html.escape(p) for p in parts)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        m = re.match(r"^(#{1,6})\s+(.*)", esc)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{m.group(2)}</h{lvl}>")
            continue
        m = re.match(r"^\s*[-*]\s+(.*)", esc)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{m.group(1)}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("</ul>")
    return "<html><body>" + "\n".join(out) + "</body></html>"


def build_message(
    path, to: list[str], cc: list[str] | None, sender: str,
    subject: str | None = None, body_text: str | None = None,
) -> EmailMessage:
    """Assemble the email. A .md report becomes the HTML body (plain text alternative
    kept) and its sibling .pdf, if present, is attached. A .pdf path is attached with a
    short body. Pure: no env, no network."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    cc = cc or []
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject or f"Wohnungsfinder report — {p.stem}"

    attachments: list[Path] = []
    if p.suffix.lower() == ".md":
        md = p.read_text(encoding="utf-8")
        msg.set_content(body_text or md)
        msg.add_alternative(markdown_to_html(md), subtype="html")
        sib = p.with_suffix(".pdf")
        if sib.exists():
            attachments.append(sib)
    else:
        msg.set_content(
            body_text or "Hi,\n\nHere is the latest apartment shortlist (PDF attached).\n\n— Wohnungsfinder"
        )
        attachments.append(p)
    for a in attachments:
        msg.add_attachment(a.read_bytes(), maintype="application", subtype="pdf", filename=a.name)
    return msg


def _smtp_settings() -> dict:
    load_env()
    missing = [k for k in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"missing email env var(s) {', '.join(missing)}; check the .env file")
    return {
        "host": os.environ["EMAIL_HOST"],
        "port": int(os.environ.get("EMAIL_PORT", "587")),
        "user": os.environ["EMAIL_HOST_USER"],
        "password": os.environ["EMAIL_HOST_PASSWORD"],
        "sender": os.environ.get("DEFAULT_FROM_EMAIL") or os.environ["EMAIL_HOST_USER"],
        "use_ssl": _bool(os.environ.get("EMAIL_USE_SSL"), default=False),
        "use_tls": _bool(os.environ.get("EMAIL_USE_TLS"), default=True),
    }


def _connect_and(s: dict, action) -> None:
    ctx = ssl.create_default_context()
    if s["use_ssl"]:
        with smtplib.SMTP_SSL(s["host"], s["port"], context=ctx) as conn:
            conn.login(s["user"], s["password"])
            action(conn)
    else:
        with smtplib.SMTP(s["host"], s["port"]) as conn:
            conn.ehlo()
            if s["use_tls"]:
                conn.starttls(context=ctx)
                conn.ehlo()
            conn.login(s["user"], s["password"])
            action(conn)


def send_report(
    path, to: list[str], cc: list[str] | None = None,
    subject: str | None = None, body_text: str | None = None,
) -> list[str]:
    """Send the report. Returns the full recipient list. Raises on missing config or
    SMTP failure (the caller surfaces it; never fail silently)."""
    s = _smtp_settings()
    msg = build_message(path, to=to, cc=cc, sender=s["sender"], subject=subject, body_text=body_text)
    recipients = list(to) + list(cc or [])
    _connect_and(s, lambda conn: conn.send_message(msg, to_addrs=recipients))
    return recipients


def verify_login() -> str:
    """Connect + authenticate without sending, to confirm credentials work."""
    s = _smtp_settings()
    _connect_and(s, lambda conn: None)
    return f"login OK as {s['user']} via {s['host']}:{s['port']}"
```

`.env.example`:

```
# Copy to .env (gitignored) and fill in. Used by `uv run wohnung email` to send reports.
# For Gmail / Google Workspace, EMAIL_HOST_PASSWORD must be an App Password
# (https://myaccount.google.com/apppasswords — requires 2FA), not your login password.
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=you@gmail.com
EMAIL_HOST_PASSWORD="xxxx xxxx xxxx xxxx"
DEFAULT_FROM_EMAIL=you@gmail.com
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
```

- [ ] **Step 5: Add the CLI subcommand**

In `wohnung/cli.py` `main()`, after the `pdf` subparser definition add:

```python
    em = sub.add_parser("email", help="email a report (.md or .pdf) to the recipients in criteria.toml [email]")
    em.add_argument("report", nargs="?", help="path to the report .md (sibling .pdf attached if present) or .pdf")
    em.add_argument("--to", action="append", help="override To recipient(s)")
    em.add_argument("--cc", action="append", help="override Cc recipient(s)")
    em.add_argument("--verify", action="store_true", help="only test SMTP login, don't send")
```

and after the `if args.cmd == "pdf":` block:

```python
    if args.cmd == "email":
        import tomllib

        from wohnung import mailer

        if args.verify:
            print(mailer.verify_login())
            return
        cfg = tomllib.loads((ROOT / "criteria.toml").read_text(encoding="utf-8")).get("email", {})
        to = args.to or cfg.get("to", [])
        cc = args.cc or cfg.get("cc", [])
        if not args.report:
            raise SystemExit("provide a report path to send (or use --verify)")
        if not to:
            raise SystemExit("no recipients: set [email].to in criteria.toml or pass --to")
        sent = mailer.send_report(args.report, to=to, cc=cc)
        print(f"emailed {args.report} to {', '.join(sent)}")
        return
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest -q`
Expected: all pass (existing + 5 new).

- [ ] **Step 7: Commit**

```bash
git add wohnung/mailer.py .env.example .gitignore pyproject.toml uv.lock wohnung/cli.py tests/test_mailer.py
git commit -m "feat: email reports via SMTP (wohnung email; creds in .env, recipients in criteria.toml)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Mode-aware config

**Files:**
- Modify: `wohnung/config.py`, `criteria.example.toml`, `tests/test_config.py`

**Interfaces:**
- Produces on `Criteria`: `mode: str` (`"rent"|"buy"`), `max_price: int`, `price_hard_cap: int`, `min_floor: int` (0 = any), `energy_class: list[str]`, `notes: str`, `email_to: list[str]`, `email_cc: list[str]`. `max_rent_kalt` / `rent_hard_cap` stay as properties aliasing the price fields for backward compatibility in tests.
- `Criteria` positional constructor order changes; `tests/test_core.py` currently builds `Criteria(1500, 1650, 60, 3, {...}, True, True)` — keep that positional order working: `(max_price, price_hard_cap, min_size_m2, min_rooms, include_districts, musthave_elevator, musthave_outdoor, ...)`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_config.py` with:

```python
from pathlib import Path

import pytest

from wohnung.config import ROOT, load_criteria

EXAMPLE = ROOT / "criteria.example.toml"

RENT_MIN = """
[budget]
max_rent_kalt = 1500
rent_hard_cap = 1650
[size]
min_size_m2 = 70
min_rooms = 3
[districts]
include = [1, 2]
[musthave]
elevator = true
outdoor = true
"""

BUY = """
[search]
mode = "buy"
[report]
language = "de"
[budget]
max_price = 450000
price_hard_cap = 500000
[size]
min_size_m2 = 70
min_rooms = 3
[districts]
include = [1, 2, 3, 4, 5, 6, 7, 8, 9]
[musthave]
elevator = false
outdoor = true
min_floor = 3
[preferences]
energy_class = ["A", "B"]
notes = \"\"\"
combined kitchen and living room
\"\"\"
[email]
to = ["friend@example.com"]
cc = ["me@example.com"]
"""


def test_load_criteria_example_template():
    c = load_criteria(EXAMPLE)
    assert c.mode == "rent"
    assert c.max_price == 1500 and c.price_hard_cap == 1650
    assert c.max_rent_kalt == 1500 and c.rent_hard_cap == 1650  # legacy aliases
    assert c.min_size_m2 == 70 and c.min_rooms == 3
    assert 1 in c.include_districts and 20 not in c.include_districts
    assert c.musthave_elevator and c.musthave_outdoor
    assert c.min_floor == 0
    assert c.energy_class == []
    assert c.notes == ""
    assert c.email_to == [] and c.email_cc == []
    assert c.report_language == "en"
    assert c.geocode_contact is None


def test_rent_profile_without_search_section_defaults_to_rent(tmp_path: Path):
    p = tmp_path / "criteria.toml"
    p.write_text(RENT_MIN, encoding="utf-8")
    c = load_criteria(p)
    assert c.mode == "rent" and c.price_hard_cap == 1650


def test_buy_profile(tmp_path: Path):
    p = tmp_path / "criteria.toml"
    p.write_text(BUY, encoding="utf-8")
    c = load_criteria(p)
    assert c.mode == "buy"
    assert c.max_price == 450000 and c.price_hard_cap == 500000
    assert c.min_floor == 3
    assert c.energy_class == ["A", "B"]
    assert "kitchen" in c.notes
    assert c.email_to == ["friend@example.com"] and c.email_cc == ["me@example.com"]
    assert c.report_language == "de"


def test_buy_profile_missing_budget_keys_names_them(tmp_path: Path):
    p = tmp_path / "criteria.toml"
    p.write_text(BUY.replace("max_price = 450000\nprice_hard_cap = 500000\n", ""), encoding="utf-8")
    with pytest.raises(SystemExit, match="max_price"):
        load_criteria(p)


def test_unknown_mode_rejected(tmp_path: Path):
    p = tmp_path / "criteria.toml"
    p.write_text(BUY.replace('mode = "buy"', 'mode = "lease"'), encoding="utf-8")
    with pytest.raises(SystemExit, match="lease"):
        load_criteria(p)


def test_missing_criteria_points_to_setup(tmp_path: Path):
    with pytest.raises(SystemExit, match="/setup"):
        load_criteria(tmp_path / "criteria.toml")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL (`AttributeError: 'Criteria' object has no attribute 'mode'` etc.)

- [ ] **Step 3: Implement**

Replace `wohnung/config.py`:

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRITERIA_PATH = ROOT / "criteria.toml"

MODES = ("rent", "buy")
# Which [budget] keys each mode reads, in (target, hard cap) order.
_BUDGET_KEYS = {"rent": ("max_rent_kalt", "rent_hard_cap"), "buy": ("max_price", "price_hard_cap")}


@dataclass
class Criteria:
    max_price: int            # target: cold rent/month (rent) or purchase price (buy)
    price_hard_cap: int       # absolute cap; listings above are dropped
    min_size_m2: int
    min_rooms: int
    include_districts: set[int]
    musthave_elevator: bool
    musthave_outdoor: bool
    geocode_contact: str | None = None
    report_language: str = "en"
    mode: str = "rent"
    min_floor: int = 0        # 0 = any; drop only when the floor is explicitly lower
    energy_class: list[str] = field(default_factory=list)  # soft preference, never a filter
    notes: str = ""           # free-text priorities, scored by the skill
    email_to: list[str] = field(default_factory=list)
    email_cc: list[str] = field(default_factory=list)

    # Legacy names used by older code/tests (rent mode).
    @property
    def max_rent_kalt(self) -> int:
        return self.max_price

    @property
    def rent_hard_cap(self) -> int:
        return self.price_hard_cap


def load_criteria(path: Path = CRITERIA_PATH) -> Criteria:
    if not path.exists():
        raise SystemExit(
            f"{path.name} not found — run /setup in Claude Code to create it "
            f"(or copy criteria.example.toml to {path.name} and edit it)"
        )
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    mode = data.get("search", {}).get("mode", "rent")
    if mode not in MODES:
        raise SystemExit(f"[search].mode = {mode!r} is not one of {MODES}")
    budget = data.get("budget", {})
    target_key, cap_key = _BUDGET_KEYS[mode]
    missing = [k for k in (target_key, cap_key) if k not in budget]
    if missing:
        raise SystemExit(
            f"[budget] is missing {', '.join(missing)} (required in {mode} mode)"
        )
    prefs = data.get("preferences", {})
    email = data.get("email", {})
    return Criteria(
        max_price=budget[target_key],
        price_hard_cap=budget[cap_key],
        min_size_m2=data["size"]["min_size_m2"],
        min_rooms=data["size"]["min_rooms"],
        include_districts=set(data["districts"]["include"]),
        musthave_elevator=data["musthave"]["elevator"],
        musthave_outdoor=data["musthave"]["outdoor"],
        geocode_contact=data.get("geocode", {}).get("contact") or None,
        report_language=data.get("report", {}).get("language", "en"),
        mode=mode,
        min_floor=int(data["musthave"].get("min_floor", 0) or 0),
        energy_class=[str(x).upper() for x in prefs.get("energy_class", [])],
        notes=str(prefs.get("notes", "")).strip(),
        email_to=list(email.get("to", [])),
        email_cc=list(email.get("cc", [])),
    )
```

- [ ] **Step 4: Update `criteria.example.toml`**

Insert after the header comment block, before `[report]`:

```toml
[search]
# "rent" (Mietwohnung) or "buy" (Eigentumswohnung). Chooses the portal search URLs,
# which [budget] keys are read, and the scoring rubric the skill applies.
mode = "rent"
```

Replace the `[budget]` section with:

```toml
[budget]
# rent mode: target cold rent (Nettomiete) and absolute cap, EUR/month
max_rent_kalt = 1500
rent_hard_cap = 1650
# buy mode: target purchase price and absolute cap, EUR. Remember ~10% side costs on top
# (Grunderwerbsteuer 3.5%, Grundbuch 1.1%, Notar, ~3.6% Provision unless provisionsfrei).
# max_price = 450000
# price_hard_cap = 500000
```

Extend `[musthave]`:

```toml
# Minimum floor (0 = any). Drops only when the listing EXPLICITLY states a lower floor;
# unknown and Dachgeschoss are kept and flagged. Erdgeschoss/Hochparterre count as 0.
min_floor = 0
```

Add after `[timing]` (before `[geocode]`):

```toml
[preferences]
# Soft preferences — scored by the skill, never a hard filter.
# Preferred HWB energy classes (Energieausweis), best first. [] = don't care.
energy_class = []
# Your own words: what matters to you, what you dislike, what's negotiable. The skill
# quotes this verbatim into its scoring, so write it the way you'd brief a friend.
notes = """
"""

[email]
# Optional. When `to` is non-empty the search skill emails each report as its final step
# via `uv run wohnung email`. SMTP credentials live in .env (see .env.example), never here.
to = []
cc = []
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add wohnung/config.py criteria.example.toml tests/test_config.py
git commit -m "feat(config): search mode, buy budget keys, min_floor, preferences, email recipients

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Generalize the model (`rent` → `price`) and add floor/energy helpers

**Files:**
- Modify: `wohnung/models.py`, all four `wohnung/sources/*.py` parsers, `wohnung/recover.py:70-82`, `wohnung/cli.py` (`_meta`), `tests/test_core.py`, `tests/test_immowelt.py`, `tests/test_other_sources.py`, `tests/test_state_recovery.py`
- Create: `wohnung/floors.py`, `wohnung/energy.py`, `tests/test_floors.py`, `tests/test_energy.py`

**Interfaces:**
- `Listing.price: float | None`, `Listing.price_kind: str` (`"kalt"|"warm"|"kauf"|"unknown"`), `Listing.price_per_m2: float | None`, `Listing.floor_number: int | None`, `Listing.energy_class: str`, `Listing.hwb: float | None`, `Listing.is_project: bool`.
- `floors.parse_floor(s: str) -> int | None`
- `energy.sniff_energy(text: str) -> tuple[str, float | None]` returning `("", None)` when nothing found.
- State/recover meta key becomes `price`; readers accept legacy `rent`.

- [ ] **Step 1: Write failing helper tests**

`tests/test_floors.py`:

```python
import pytest

from wohnung.floors import parse_floor


@pytest.mark.parametrize("s,expected", [
    ("3", 3), ("3. Stock", 3), ("3. OG", 3), ("3.OG", 3), ("3. Geschoss", 3), ("3. Etage", 3),
    ("12", 12), ("1. Stock mit Lift", 1),
    ("EG", 0), ("Erdgeschoss", 0), ("Parterre", 0), ("Hochparterre", 0), ("HP", 0),
    ("DG", None), ("Dachgeschoss", None), ("", None), ("Souterrain", None), ("Maisonette", None),
])
def test_parse_floor(s, expected):
    assert parse_floor(s) == expected
```

`tests/test_energy.py`:

```python
import pytest

from wohnung.energy import sniff_energy


@pytest.mark.parametrize("text,cls,hwb", [
    ("Energieklasse A, HWB 25 kWh/m²a", "A", 25.0),
    ("HWB-Klasse: B", "B", None),
    ("Heizwärmebedarf 45,5 kWh/m²a (Klasse C)", "C", 45.5),
    ("HWB 120.3 kWh", "", 120.3),
    ("Energieausweis liegt vor", "", None),
    ("", "", None),
    ("finalEnergyDemandClass\":\"D\"", "D", None),
])
def test_sniff_energy(text, cls, hwb):
    assert sniff_energy(text) == (cls, hwb)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_floors.py tests/test_energy.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement helpers**

`wohnung/floors.py`:

```python
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
```

`wohnung/energy.py`:

```python
"""Best-effort energy certificate sniffing from listing text or embedded JSON."""

from __future__ import annotations

import re

_CLASS = re.compile(
    r"(?:energieklasse|hwb[-\s]?klasse|klasse|finalEnergyDemandClass\W+)\s*[:\"]?\s*([A-G])(?:\+{0,2})\b",
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
```

Run: `uv run pytest tests/test_floors.py tests/test_energy.py -q` → PASS. Adjust regexes if a parametrized case fails; do not loosen the test.

- [ ] **Step 4: Rename the model field and add new fields**

In `wohnung/models.py` replace the two rent lines with:

```python
    price: Optional[float] = None  # monthly rent (rent mode) or purchase price (buy mode)
    price_kind: str = "unknown"  # "kalt" | "warm" | "kauf" | "unknown"
    price_per_m2: Optional[float] = None  # computed in run_search when price and size exist
```

and after `floor: str = ""` add:

```python
    floor_number: Optional[int] = None  # parsed from `floor`; None = unknown / DG
```

and after `building_condition` add:

```python
    energy_class: str = ""  # HWB class "A".."G", "" if unknown
    hwb: Optional[float] = None  # kWh/m²a
    is_project: bool = False  # developer/Bauträger project: price is a from-price, size may be None
```

Mechanically rename `rent=` → `price=` in the four parsers (`willhaben.py:73`, `immoscout.py:84`, `derstandard.py:59`, `immowelt.py:63`) and `l.rent` → `l.price` in tests (`test_immowelt.py`, `test_other_sources.py`, `test_state_recovery.py`, `test_core.py`).

- [ ] **Step 5: Meta key `price` with legacy `rent` fallback**

`wohnung/cli.py` `_meta`:

```python
    def _meta(l):  # fingerprint inputs, persisted so the dedup key survives/recomputes
        return {"district": l.district, "rooms": l.rooms, "size_m2": l.size_m2, "price": l.price}
```

`wohnung/dedup.py` add a helper used by both state and recover:

```python
def meta_price(meta: dict) -> Optional[float]:
    """Price from a persisted meta dict; accepts the legacy 'rent' key."""
    v = meta.get("price")
    return v if v is not None else meta.get("rent")
```

`wohnung/state.py` `_collect_fingerprints`: replace `m.get("rent")` with `meta_price(m)` (import `meta_price` from `wohnung.dedup`).

`wohnung/recover.py:74-81`: build meta from keys `("district", "rooms", "size_m2", "price", "rent")`, then call `fingerprint_from(meta.get("district"), meta.get("rooms"), meta.get("size_m2"), meta_price(meta))`.

`tests/test_state_recovery.py:68` keep the legacy `"rent": 1549` meta in that one test (it now proves the fallback) and add:

```python
def test_state_recomputes_fingerprint_from_legacy_rent_meta(tmp_path):
    p = tmp_path / "seen.json"
    State(p).record("a", source="s", url="u", meta={"district": 3, "rooms": 3, "size_m2": 60, "rent": 1549})
    st = State(p)
    assert st.has_fingerprint(fingerprint_from(3, 3, 60, 1549))
```

(import `fingerprint_from` from `wohnung.dedup` at the top of that test file if missing.)

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass. `grep -rn "\.rent\b\|rent=" wohnung tests` should return only `rent_hard_cap`/`max_rent_kalt` and the legacy-meta test.

- [ ] **Step 7: Commit**

```bash
git add wohnung/models.py wohnung/floors.py wohnung/energy.py wohnung/dedup.py wohnung/state.py wohnung/recover.py wohnung/cli.py wohnung/sources/*.py tests/
git commit -m "refactor(model): rent -> price/price_kind; add floor_number, energy_class, hwb, is_project helpers

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Filters and mode-aware dedup

**Files:**
- Modify: `wohnung/filters.py`, `wohnung/dedup.py`, `wohnung/state.py`, `wohnung/recover.py`, `wohnung/cli.py` (State construction), `tests/test_core.py`, `tests/test_immowelt.py`

**Interfaces:**
- `hard_filter(l, c)` unchanged signature; reads `c.price_hard_cap`, `c.min_floor`.
- `fingerprint_from(district, rooms, size_m2, price, mode="rent")`, `fingerprint(l, mode="rent")`; rounding step `PRICE_STEP = {"rent": 10, "buy": 1000}`.
- `State(path, mode="rent")` recomputes fingerprints with that mode.

- [ ] **Step 1: Failing tests**

Append to `tests/test_core.py`:

```python
from wohnung.dedup import fingerprint, fingerprint_from

BUY = Criteria(450000, 500000, 70, 3, set(range(1, 10)), False, True, mode="buy", min_floor=3)


def _buy(**kw):
    d = dict(district=4, price=480000, size_m2=80, rooms=3, has_outdoor=True, floor_number=4)
    d.update(kw)
    return Listing(id="b", source="s", url="u", **d)


def test_hard_filter_buy_price_cap_and_floor():
    assert hard_filter(_buy(), BUY)[0]
    assert hard_filter(_buy(price=500000), BUY)[0]          # at cap: keep
    assert not hard_filter(_buy(price=500001), BUY)[0]
    assert not hard_filter(_buy(floor_number=2), BUY)[0]     # explicitly lower: drop
    assert hard_filter(_buy(floor_number=None, floor="DG"), BUY)[0]  # unknown/DG: keep
    assert hard_filter(_buy(floor_number=0), C)[0]           # min_floor=0 -> no floor filter
    assert hard_filter(_buy(size_m2=None), BUY)[0]           # project without size: keep


def test_fingerprint_rounding_per_mode():
    assert fingerprint_from(4, 3, 80, 479500, mode="buy") == fingerprint_from(4, 3, 80, 480400, mode="buy")
    assert fingerprint_from(4, 3, 80, 479500, mode="buy") != fingerprint_from(4, 3, 80, 481000, mode="buy")
    assert fingerprint_from(7, 3, 70, 1198) == fingerprint_from(7, 3, 70, 1202)   # rent default: 10
    assert fingerprint_from(7, 3, 70, 1198) != fingerprint_from(7, 3, 70, 1215)


def test_state_uses_mode_for_fingerprints(tmp_path):
    p = tmp_path / "seen.json"
    State(p, mode="buy").record("a", source="s", url="u",
                                meta={"district": 4, "rooms": 3, "size_m2": 80, "price": 479500})
    assert State(p, mode="buy").has_fingerprint(fingerprint_from(4, 3, 80, 480400, mode="buy"))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_core.py -q` → FAIL (`TypeError: unexpected keyword 'mode'`).

- [ ] **Step 3: Implement**

`wohnung/filters.py`:

```python
def hard_filter(l: Listing, c: Criteria) -> tuple[bool, str]:
    """Return (keep, reason_if_dropped). Elevator/outdoor/floor only drop when EXPLICITLY
    absent or below (unknown is kept and flagged later)."""
    if l.district is not None and l.district not in c.include_districts:
        return False, f"district {l.district} excluded"
    if l.price is not None and l.price > c.price_hard_cap:
        return False, f"price {l.price:.0f} over cap {c.price_hard_cap}"
    if l.size_m2 is not None and l.size_m2 < c.min_size_m2:
        return False, f"size {l.size_m2:.0f} below {c.min_size_m2}"
    if l.rooms is not None and l.rooms < c.min_rooms:
        return False, f"rooms {l.rooms:.0f} below {c.min_rooms}"
    if c.musthave_elevator and l.has_elevator is False:
        return False, "no elevator (explicit)"
    if c.musthave_outdoor and l.has_outdoor is False:
        return False, "no outdoor space (explicit)"
    if c.min_floor and l.floor_number is not None and l.floor_number < c.min_floor:
        return False, f"floor {l.floor_number} below {c.min_floor} (explicit)"
    return True, ""
```

`wohnung/dedup.py`:

```python
PRICE_STEP = {"rent": 10, "buy": 1000}  # tolerance for cross-post price differences


def fingerprint_from(district, rooms, size_m2, price, mode: str = "rent") -> Optional[str]:
    if district is None or size_m2 is None or price is None:
        return None
    step = PRICE_STEP.get(mode, 10)
    size = round(size_m2)
    p = round(price / step) * step
    r = round(rooms) if rooms is not None else "?"
    return f"{district}|{r}|{size}|{p}"


def fingerprint(l: Listing, mode: str = "rent") -> Optional[str]:
    return fingerprint_from(l.district, l.rooms, l.size_m2, l.price, mode=mode)
```

`wohnung/state.py`: `def __init__(self, path: Path, mode: str = "rent")`, store `self.mode = mode`, and pass `mode=self.mode` in `_collect_fingerprints`. `wohnung/recover.py`: `reindex(root, mode="rent")` → `State(..., mode=mode)` and `fingerprint_from(..., mode=mode)`. `wohnung/cli.py`: `State(root / "state" / "seen.json", mode=c.mode)`, `fingerprint(l, mode=c.mode)`, and in the `mark`/`reindex` branches load criteria for the mode (`load_criteria().mode`; if `criteria.toml` is missing, `mark` still works with the default).

- [ ] **Step 4: Run the suite** → `uv run pytest -q` all pass.

- [ ] **Step 5: Commit**

```bash
git add wohnung/filters.py wohnung/dedup.py wohnung/state.py wohnung/recover.py wohnung/cli.py tests/test_core.py
git commit -m "feat: price cap + min_floor hard filters; mode-aware dedup fingerprint

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Sources — buy URLs, project hits, floor and energy extraction

**Files:**
- Modify: `wohnung/sources/willhaben_client.py`, `immoscout_client.py`, `derstandard_client.py`, `immowelt_client.py`, `wohnung/sources/immoscout.py`, `wohnung/sources/willhaben.py`, `wohnung/sources/immowelt.py`, `wohnung/cli.py` (`build_sources`)
- Create: `tests/fixtures/immoscout_buy_search.html`, `tests/fixtures/immoscout_buy_detail.html`, `tests/fixtures/immowelt_buy_search.html`, `tests/test_buy_sources.py`

**Interfaces:**
- Every client: `__init__(self, fetcher, mode: str = "rent")`, class attr `SEARCH_URLS: dict[str, str]`, sets `listing.price_kind = "kauf"` in buy mode on every listing returned by `search()`.
- `build_sources(fetcher, mode: str = "rent")`.
- `immoscout.parse_search(html)` keeps hits with a numeric `primaryPrice` even when `primaryArea` is missing, setting `is_project=True` and `size_m2=None`; `immoscout.sniff_detail(html) -> dict` with keys `floor` (str), `energy_class`, `hwb`, `year_built` (int|None).

- [ ] **Step 1: Copy fixtures**

```bash
S=/private/tmp/claude-501/-Users-biagio-repos-personal-wohnungfinder/ae0e8b58-da63-45a8-ad46-1480aeb1beef/scratchpad
cp "$S/immoscout_buy.html" tests/fixtures/immoscout_buy_search.html
cp "$S/immoscout_buy_detail.html" tests/fixtures/immoscout_buy_detail.html
cp "$S/immowelt_buy.html" tests/fixtures/immowelt_buy_search.html
ls -la tests/fixtures/
```

- [ ] **Step 2: Failing tests**

`tests/test_buy_sources.py`:

```python
"""Buy-mode parsing against saved fixtures. willhaben/derStandard buy fixtures are
optional (their sites 403 plain HTTP); tests skip when the file is absent."""

from pathlib import Path

import pytest

from wohnung.fetch import Fetcher
from wohnung.sources import immoscout as im
from wohnung.sources import immowelt as iw
from wohnung.sources.immoscout_client import ImmoScoutSource
from wohnung.sources.immowelt_client import ImmoweltSource
from wohnung.sources.willhaben_client import WillhabenSource
from wohnung.sources.derstandard_client import DerStandardSource

FIX = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    p = FIX / name
    if not p.exists():
        pytest.skip(f"fixture {name} not captured")
    return p.read_text(encoding="utf-8")


def test_immoscout_buy_keeps_developer_projects():
    listings = im.parse_search(_read("immoscout_buy_search.html"))
    assert len(listings) >= 10
    projects = [l for l in listings if l.is_project]
    assert projects, "developer hits with area ranges must be kept, flagged is_project"
    p = projects[0]
    assert p.price and p.price > 100000
    assert p.size_m2 is None
    assert p.district and 1 <= p.district <= 23
    assert p.url.startswith("https://www.immobilienscout24.at/expose/")


def test_immoscout_detail_sniff_has_expected_keys():
    d = im.sniff_detail(_read("immoscout_buy_detail.html"))
    assert set(d) == {"floor", "energy_class", "hwb", "year_built"}
    assert isinstance(d["floor"], str)


def test_immowelt_buy_cards_carry_price_and_floor():
    listings = iw.parse_search(_read("immowelt_buy_search.html"))
    assert len(listings) >= 20
    l = next(x for x in listings if x.floor)
    assert l.price and l.price > 100000
    assert l.floor_number is not None or l.floor  # "3" -> 3; "DG"-like stays as string


def test_buy_urls_and_price_kind():
    f = Fetcher()
    for cls, key in ((WillhabenSource, "eigentumswohnung"), (ImmoScoutSource, "wohnung-kaufen"),
                     (DerStandardSource, "kaufen-wohnung"), (ImmoweltSource, "wohnungen/kaufen")):
        src = cls(f, mode="buy")
        assert key in src.search_url
        assert "miet" in cls(f).search_url or "mieten" in cls(f).search_url
    f.close()


def test_immowelt_search_marks_kauf(monkeypatch):
    html = _read("immowelt_buy_search.html")

    class F:
        def get(self, url, params=None): return html
    src = ImmoweltSource(F(), mode="buy")
    out = src.search(max_pages=1)
    assert out and all(l.price_kind == "kauf" for l in out)
    assert all(l.floor_number is not None for l in out if l.floor and l.floor[0].isdigit())
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_buy_sources.py -q` → FAIL (`TypeError: __init__() got an unexpected keyword argument 'mode'`, `AttributeError: sniff_detail`).

- [ ] **Step 4: Implement the clients**

Shared shape (apply to all four; shown for willhaben):

```python
SEARCH_URLS = {
    "rent": "https://www.willhaben.at/iad/immobilien/mietwohnungen/wien",
    "buy": "https://www.willhaben.at/iad/immobilien/eigentumswohnung/wien",
}


class WillhabenSource:
    name = "willhaben"

    def __init__(self, fetcher: Fetcher, mode: str = "rent"):
        self.f = fetcher
        self.mode = mode
        self.search_url = SEARCH_URLS[mode]

    def _stamp(self, listings):
        for l in listings:
            if self.mode == "buy":
                l.price_kind = "kauf"
            l.floor_number = parse_floor(l.floor)
        return listings
```

Every `search()` uses `self.search_url` in place of the module constant and returns `self._stamp(out)`. Every `enrich()` ends with `listing.floor_number = parse_floor(listing.floor)` (floor may arrive from the detail page) and, where text is available, `listing.energy_class, listing.hwb = sniff_energy(text)` unless already set.

Per-source URLs:

- immoscout: `rent: https://www.immobilienscout24.at/regional/wien/wien/wohnung-mieten`, `buy: .../wohnung-kaufen`; pagination stays `f"{self.search_url}/seite-{page}"`.
- derStandard: `rent: https://immobilien.derstandard.at/suche/wien/mieten-wohnung`, `buy: .../kaufen-wohnung`.
- immowelt: `rent: https://www.immowelt.at/liste/wien/wohnungen/mieten`, `buy: .../wohnungen/kaufen`.

Willhaben energy: in `willhaben.parse_detail`, after `a = _attrs(ad)`, read `a.get("HWB_CLASS") or a.get("ENERGY_CLASS") or ""` into `energy_class` (upper-cased first letter) and `_num(a.get("HWB_VALUE"))` into `hwb`; if both empty, fall back to `sniff_energy(a.get("DESCRIPTION", ""))`. (Attribute names are unverified — the fixture is rent and has none; keep the text fallback so nothing depends on the guess.) In `willhaben_client.enrich`, copy `det.energy_class` / `det.hwb` onto the listing.

- [ ] **Step 5: Implement immoscout project hits and detail sniff**

In `wohnung/sources/immoscout.py` `parse_search`, replace the skip:

```python
        eid = hit.get("exposeId")
        price = _to_float(hit.get("primaryPrice"))
        area = _to_float(hit.get("primaryArea"))
        if not eid or price is None:
            continue  # nothing to filter on
        is_project = area is None or str(hit.get("displayType", "")).startswith("DEVELOPER")
```

and pass `size_m2=area, is_project=is_project` and store `hit.get("mainKeyFacts")` in `raw["hit"]["mainKeyFacts"]`. For projects, if `numberOfRooms` is missing, parse the first integer in the `mainKeyFacts` entry labelled `"Zimmer"` (e.g. `"2 – 3"` → 2) so the rooms filter can still drop 1–2 room projects.

Add:

```python
_DETAIL_KEYS = {
    "floor": re.compile(r'"floorLabel":\s*"([^"]*)"'),
    "floor_num": re.compile(r'"floor":\s*(\d+)'),
    "energy_class": re.compile(r'"finalEnergyDemandClass":\s*"([A-G])'),
    "hwb": re.compile(r'"finalEnergyDemand":\s*([\d.]+)'),
    "year_built": re.compile(r'"yearOfConstruction":\s*(\d{4})'),
}


def sniff_detail(html: str) -> dict:
    """Pull floor / energy / build year out of the expose page's embedded JSON.
    Values are often null on IS24; missing -> '' / None."""
    g = {k: (m.group(1) if (m := rx.search(html)) else None) for k, rx in _DETAIL_KEYS.items()}
    floor = g["floor"] or (g["floor_num"] if g["floor_num"] else "")
    cls, hwb = g["energy_class"] or "", float(g["hwb"]) if g["hwb"] else None
    if not cls:
        cls2, hwb2 = sniff_energy(re.sub(r"<[^>]+>", " ", html))
        cls, hwb = cls2, hwb or hwb2
    return {"floor": floor, "energy_class": cls, "hwb": hwb,
            "year_built": int(g["year_built"]) if g["year_built"] else None}
```

In `immoscout_client.enrich`, after the equipment sniff: `d = im.sniff_detail(html)`; `listing.floor = listing.floor or d["floor"]`; `listing.energy_class = listing.energy_class or d["energy_class"]`; `listing.hwb = listing.hwb or d["hwb"]`; `listing.floor_number = parse_floor(listing.floor)`.

- [ ] **Step 6: Wire `build_sources(fetcher, mode)`**

`wohnung/cli.py`:

```python
def build_sources(fetcher: Fetcher, mode: str = "rent") -> list:
    ...
            sources.append(getattr(mod, class_name)(fetcher, mode=mode))
```

and in `run_search`: `for src in build_sources(fetcher, c.mode):`.

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest -q` → all pass (existing rent fixtures must still parse; `test_immoscout_parses_real_listings` may now return projects first — if `listings[0]` is a project without `size_m2`, change that test to pick `next(l for l in listings if not l.is_project)`).

- [ ] **Step 8: Commit**

```bash
git add wohnung/sources/ wohnung/cli.py tests/test_buy_sources.py tests/test_other_sources.py tests/fixtures/immoscout_buy_search.html tests/fixtures/immoscout_buy_detail.html tests/fixtures/immowelt_buy_search.html
git commit -m "feat(sources): buy-mode search URLs, developer-project hits, floor and energy extraction

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `run_search` output — €/m², mode, and CLI summary

**Files:**
- Modify: `wohnung/cli.py` (`run_search`, `main`), `tests/test_core.py`

**Interfaces:**
- `.last_run.json` gains top-level `"mode": c.mode`; each listing has `price_per_m2` (rounded to 0 decimals) when `price` and `size_m2` exist.
- `run_search(root, max_pages, download)` unchanged signature.

- [ ] **Step 1: Failing test**

Append to `tests/test_core.py`:

```python
from wohnung.cli import price_per_m2


def test_price_per_m2():
    assert price_per_m2(_buy(price=480000, size_m2=80)) == 6000
    assert price_per_m2(_buy(size_m2=None)) is None
    assert price_per_m2(_buy(price=None)) is None
```

- [ ] **Step 2: Run** → FAIL (`ImportError`).

- [ ] **Step 3: Implement**

In `wohnung/cli.py`:

```python
def price_per_m2(l) -> float | None:
    if l.price and l.size_m2:
        return round(l.price / l.size_m2)
    return None
```

In `run_search`, right before `download_images(...)`: `l.price_per_m2 = price_per_m2(l)`. In the `out` dict add `"mode": c.mode,`. In `main()` search summary print, prefix with `f"mode: {out['mode']}  "`.

- [ ] **Step 4: Run** → `uv run pytest -q` all pass. Also smoke: `uv run wohnung --help` and `uv run wohnung email --help`.

- [ ] **Step 5: Commit**

```bash
git add wohnung/cli.py tests/test_core.py
git commit -m "feat(search): price_per_m2 and mode in .last_run.json

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Skills, commands, README

**Files:**
- Modify: `.claude/skills/wohnung-search/SKILL.md`, `.claude/skills/setup/SKILL.md`, `.claude/commands/wohnung-search.md`, `.claude/commands/setup.md`, `README.md`

No automated tests; verification is a careful read plus `uv run pytest -q` still green.

- [ ] **Step 1: `wohnung-search` skill**

Edits, in order:

1. Intro paragraph: "hunts for an apartment in Vienna — **to rent or to buy**, per `[search].mode` in `criteria.toml`".
2. "The search profile" list: add `mode`, `min_floor`, `[preferences].energy_class` and `.notes`, `[email]`. Add a bullet: "**`[preferences].notes` is the user's own wish list. Quote it back to yourself before scoring and score against it explicitly** — it can override the generic rubric below."
3. Step 2 source URLs: list both rent and buy URLs per portal (the four buy URLs from Task 5). Tell the model to use the one matching `mode`.
4. Step 3: `.last_run.json` now has `mode`; listings have `price`, `price_kind` (`kauf` in buy mode), `price_per_m2`, `floor`, `floor_number`, `energy_class`, `hwb`, `is_project`.
5. Step 5 becomes two sub-rubrics. Keep the existing one under **"Rent mode"**. Add **"Buy mode"** (weights in this order):
   - Price per m² versus the district's typical range (say which range you assumed); headroom below `max_price`.
   - `[preferences].energy_class`: match = strong plus, worse = strong minus, unknown = say "energy class unknown" and look for HWB/Energieklasse in the description. **Never drop on it.**
   - Floor: `floor_number` ≥ `min_floor`; higher and view-facing (description/photos) better; `null` with `floor` text like "DG" = say "Dachgeschoss / floor unconfirmed".
   - Outdoor space (confirmed vs unknown), as in rent mode.
   - Layout from the floor plan: combined kitchen-living (or obviously movable partition walls) = plus; bath/WC adjacency as in rent mode.
   - Condition from photos + description: "sanierungsbedürftig / renovierungsbedürftig" is acceptable **only** if the €/m² is clearly below the district range — say so explicitly.
   - Betriebskosten / Rücklage / Hausverwaltung costs if stated; Altbau vs Neubau; `provisionsfrei`.
   - `is_project` listings: separate short section "Bauträger projects" — from-price, unit ranges, note that energy class is usually A/B and the concrete unit must be checked.
   - Skip move-in timing and the furnished penalty in buy mode.
6. Step 6 report fields: add price kind, €/m², floor, energy class; header line in buy mode: "Purchase side costs ≈ 10 % on top (Grunderwerbsteuer 3.5 %, Eintragung 1.1 %, Notar; ~3.6 % + VAT Provision unless provisionsfrei)".
7. New step after the PDF step: **"Email the report"** — if `[email].to` is non-empty **and** there is ≥ 1 new listing: run `uv run wohnung pdf reports/<name>.md` (skip if pandoc missing), then `uv run wohnung email reports/<name>.md`. On any error, state it in the inline summary ("report saved but email failed: …"); never swallow it. If `to` is empty, skip silently.
8. Notes: replace "Rent kalt vs warm…" bullet to mention it applies to rent mode; add "In buy mode, if many listings are excluded on `price over cap`, suggest raising `price_hard_cap`."

- [ ] **Step 2: `setup` skill**

Interview changes: question 1 becomes "**Rent or buy?**" (writes `[search].mode`). Question 2 (budget) branches: rent asks cold rent + cap; buy asks target purchase price + hard cap and mentions the ~10 % side costs. After must-haves add "**Minimum floor?** (0 = any; explained: drops only when explicitly lower)". Skip questions 6 (furnished) and 7 (timing) in buy mode. Add "**Energy class preference**" (list, or none) and "**Your wish list in your own words**" → `[preferences].notes`. Add "**Email the reports?**" → `[email].to/cc`, then instruct: copy `.env.example` to `.env`, fill SMTP creds (Gmail app password), and run `uv run wohnung email --verify`. Section 3 verification adds `uv run wohnung email --verify` when `[email].to` is set.

- [ ] **Step 3: Commands and README**

`.claude/commands/wohnung-search.md` description: "Search Vienna portals for new apartments (rent or buy, per criteria.toml) …". `.claude/commands/setup.md`: mention rent/buy and email.

README:
- Title paragraph: "rental **or purchase** portals".
- Quick start: `/setup` bullet "rent or buy, budget, …".
- "How a search run works" step 1: "(rent cap or purchase-price cap, size, rooms, districts, minimum floor)"; step 2 add "energy class, €/m²".
- Sources table: add a "Buy URL" column with the four buy paths.
- New subsection **"Buying instead of renting"**: `[search] mode = "buy"`, `[budget] max_price/price_hard_cap`, `min_floor`, `[preferences]`, developer-project handling, side-costs reminder.
- **Privacy model**: replace "Nothing is sent anywhere: no email…" with "Nothing is sent anywhere by default. If you fill in `[email]` in `criteria.toml` and SMTP credentials in `.env` (gitignored, see `.env.example`), the search skill emails each report to those addresses via your own SMTP account." Add `.env` to the local-only table.
- CLI list: add `uv run wohnung email reports/<name>.md` and `--verify`.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest -q` (still green) and re-read both SKILL.md files top to bottom once for contradictions with the rent flow.

```bash
git add .claude/ README.md
git commit -m "docs(skills): buy-mode rubric, email step, setup interview for mode/floor/energy/notes/email

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Apply the friend's profile locally (not committed)

**Files:**
- Modify: `criteria.toml` (gitignored)
- Create: `.env` (gitignored) — **only the template**; the user fills in the app password.

- [ ] **Step 1: Back up the current rent profile**

```bash
cp criteria.toml criteria.rent-backup.toml   # gitignored? check: `git check-ignore criteria.rent-backup.toml` — if not ignored, put it in ~/ instead
```

- [ ] **Step 2: Write `criteria.toml`**

```toml
# Search profile — personal, gitignored. Regenerate with /setup or from criteria.example.toml.

[search]
mode = "buy"

[report]
language = "en"

[budget]
max_price = 500000
price_hard_cap = 500000     # her stated max; side costs (~10%) come on top

[size]
min_size_m2 = 70
min_rooms = 3

[districts]
include = [1, 2, 3, 4, 5, 6, 7, 8, 9]

[musthave]
elevator = false            # not on her list; floor >= 3 without a lift gets flagged by the skill
outdoor = true              # balcony / terrace / loggia
min_floor = 3

[preferences]
energy_class = ["A", "B"]
notes = """
Ideal dream fantasy:
- District 1-9
- 70 m² and up
- 3 rooms, combined kitchen and living room, or possible to take down / put up walls
- Max 500.000 EUR
- Floor: 3rd and up, ideally with a view
- With balcony or terrace or something
- Not in extremely bad shape; a little renovation is ok, but then the price must be lower
- HWB Energieklasse: A or B
"""

[email]
to = ["FRIEND@EXAMPLE.COM"]    # <- fill in
cc = ["biagio@biagiodistefano.io"]

[geocode]
contact = ""
```

- [ ] **Step 3: `.env`**

```bash
cp .env.example .env
```

Leave the password for the user to fill in. Then: `uv run wohnung email --verify` (expected to fail until filled).

- [ ] **Step 4: Dry run without images**

```bash
uv run wohnung search --max-pages 1 --no-images
```

Expected: `mode: buy` in the summary, immoscout + immowelt listings, willhaben + derStandard under errors with 403. Check `reports/.last_run.json` has `"mode": "buy"` and listings with `price_kind: "kauf"`.

No commit for this task.

---

## Self-review

- **Spec coverage:** §1 mode switch → Task 2; §2 model → Task 3; §3 filters/dedup → Task 4; §4 sources → Task 5; §5 skill → Task 7; §6 email → Task 1 (+7 for the skill step); §7 setup → Task 7; §8 tests → Tasks 1–6; friend's profile → Task 8. willhaben/derStandard buy fixtures: skipped when absent (spec said capture via browser; Playwright MCP is down this session — capture later and un-skip).
- **Placeholders:** willhaben energy attribute names (`HWB_CLASS`, `ENERGY_CLASS`, `HWB_VALUE`) are explicitly labeled unverified with a text fallback; not a placeholder but a known guess. Friend's email address is the one genuine blank for the user.
- **Type consistency:** `Criteria(max_price, price_hard_cap, …, mode=, min_floor=)` used identically in Tasks 2, 4. `fingerprint_from(..., mode=)` in Tasks 3–4. `parse_floor` / `sniff_energy` names consistent across Tasks 3, 5. `price_per_m2` defined in Task 6 and referenced in Task 7's skill text.
