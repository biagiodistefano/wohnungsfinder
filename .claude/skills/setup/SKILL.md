---
name: setup
description: First-run interview that creates the personal search profile (criteria.toml) — rent or buy, budget, districts, must-haves, wish list, report language, optional email delivery — installs dependencies, and optionally schedules unattended searches. Use when the user runs /setup, when criteria.toml is missing, or when the user wants to change their search preferences.
---

# Wohnungsfinder setup interview

Create (or update) the user's personal search profile. The profile lives in
`criteria.toml` at the repo root — **gitignored, personal, never committed**.
`criteria.example.toml` is the annotated template; read it first so you know
every field and its meaning.

If `criteria.toml` already exists, read it and tell the user their current
settings; the interview then updates only what they want changed.

## 1. Interview

Use the AskUserQuestion tool (fall back to plain questions if unavailable).
Group related questions; don't ask more than ~4 at a time. Ask, in order:

1. **Rent or buy?** — are they looking for a Mietwohnung or an Eigentumswohnung?
   Store `[search] mode = "rent"` or `"buy"`. Everything below adapts to it.
2. **Report language** — which language should the ranked reports be written in?
   Offer English / Deutsch / Italiano plus free-form. Store the ISO code
   (`en`, `de`, `it`, ...) in `[report] language`. From this point on, if the user
   picked a non-English language, it's a nice touch to continue the interview in it.
3. **Budget** —
   - *rent:* target cold rent (Nettomiete) per month, and the absolute hard cap above
     which listings are dropped (suggest ~10% above target). Store `max_rent_kalt`,
     `rent_hard_cap`.
   - *buy:* target purchase price and the absolute hard cap. Mention that side costs
     add roughly 10% on top (Grunderwerbsteuer 3.5%, Grundbuch 1.1%, Notar, ~3.6%
     Provision unless provisionsfrei) so the cap should be what they can pay *before*
     those. Store `max_price`, `price_hard_cap`.
4. **Size** — minimum m² and minimum Zimmer count (explain the Austrian
   convention: the living room counts as a Zimmer).
5. **Districts** — which Vienna districts (1–23) to include. Offer shortcuts:
   "inside the Gürtel" (1–9), "everything except across the Danube" (all but
   20/21/22), "everywhere" (1–23), or a custom list.
6. **Must-haves** — elevator? outdoor space (balcony/terrace/loggia/garden)?
   minimum floor (0 = any)? Explain the semantics: a must-have hard-drops a listing
   only when it's *explicitly* absent (or the floor is explicitly lower); unknown is
   kept and flagged. Erdgeschoss/Hochparterre count as floor 0; Dachgeschoss is
   treated as unknown and kept.
7. **Furnished** *(rent only)* — is a fully furnished (möbliert) flat a downside for
   them? (`penalize_furnished`)
8. **Move-in timing** *(rent only)* — when does their current lease end (if
   applicable), and what's the ideal move-in date? Overlap tolerance defaults: min 2
   weeks, max 2 months. If timing doesn't matter, set `lease_ends = ""`.
9. **Energy class preference** — do they care about the HWB energy class
   (Energieausweis)? If yes, which classes are acceptable (e.g. A and B)? Store as
   `[preferences] energy_class = ["A", "B"]`; `[]` if they don't care. Explain it's a
   soft preference: scored and always reported, never a hard filter (portal data is
   patchy and a great flat shouldn't vanish over a missing certificate).
10. **Their wish list, in their own words** — ask them to describe (or paste) what
    matters: layout wishes, view, condition tolerance, dealbreakers, anything. Store
    verbatim in `[preferences] notes = """..."""`. The search skill scores against
    this text explicitly, so it can hold things no structured field covers.
11. **Email the reports?** — optional. If yes, collect To and Cc addresses into
    `[email] to = [...]`, `cc = [...]`. Then tell them: copy `.env.example` to `.env`
    and fill in the SMTP login (for Gmail, an App Password from
    https://myaccount.google.com/apppasswords — needs 2FA). `.env` is gitignored.
12. **Geocoder contact** (optional) — an email address or URL for the Nominatim
    User-Agent, per OSM's usage policy. Explain it's only sent to
    nominatim.openstreetmap.org, stays in the gitignored criteria.toml, and can
    be left empty.

## 2. Write `criteria.toml`

Copy the structure (and comments) of `criteria.example.toml`, filling in the
answers. In buy mode, write `max_price`/`price_hard_cap` in `[budget]` and leave the
rent keys out (or commented); `[furnished]` and `[timing]` can be omitted. Keep it
human-editable. Show the user a short summary of what you wrote.

## 3. Install & verify

```bash
uv sync                 # creates .venv and installs the package + dev deps
uv run wohnung --help   # smoke test
uv run pytest -q        # offline parser tests — should all pass
```

If `[email].to` is set and they've filled in `.env`:

```bash
uv run wohnung email --verify   # SMTP login check, sends nothing
```

If `uv` is missing, point the user to https://docs.astral.sh/uv/ (macOS:
`brew install uv`). If `pandoc` is missing, mention PDF export (and the PDF
attachment on emails) won't work until `brew install pandoc` (optional —
everything else works without it).

## 4. Optional: scheduled runs (macOS)

Ask whether they want unattended twice-daily searches. If yes:

```bash
sed "s|__REPO__|$(pwd)|g" scripts/local.wohnungsfinder.search.plist \
  > ~/Library/LaunchAgents/local.wohnungsfinder.search.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.wohnungsfinder.search.plist
```

Warn them: the unattended script runs Claude with
`--dangerously-skip-permissions` (see `scripts/wohnung-cron.sh`) — they should
be comfortable with that before enabling it. Times are edited in the plist
(`StartCalendarInterval`). To disable:
`launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/local.wohnungsfinder.search.plist`.

## 5. Finish

Tell the user setup is complete and they can run `/wohnung-search` for their
first search. Remind them their profile is personal and gitignored — safe from
accidental commits — and can be re-run with `/setup` or edited by hand anytime.
