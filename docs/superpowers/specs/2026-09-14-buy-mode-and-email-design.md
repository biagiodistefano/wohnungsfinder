# Buy mode + email delivery — design

Date: 2026-09-14. Status: draft for review.

## Goal

Let Wohnungsfinder hunt for apartments **to buy** (Eigentumswohnung) as well as to
rent, driven by the same profile file and the same Claude skill, and **email each
report** to a configurable recipient list at the end of unattended runs. The public
repo keeps rent mode fully working; this checkout is switched to buy mode for a
friend's search.

Non-goals (explicitly out of scope): fetching rent and buy in one run; Genossenschaft /
co-op sources; a new source for Bauträger project portals; fixing the willhaben and
derStandard 403 bot-block (pre-existing, handled by the Playwright fallback in the
skill; a `curl_cffi` impersonation spike is a candidate follow-up).

## The friend's profile (drives the buy criteria)

Districts 1–9 · ≥ 70 m² · ≥ 3 rooms · max € 500 000 · floor 3 or higher, ideally with a
view · balcony/terrace/loggia · combined kitchen-living or walls that can be moved ·
condition not terrible, light renovation OK if the price reflects it · HWB energy class
A or B.

Mapping to layers:

| Wish | Layer | How |
|---|---|---|
| Districts 1–9 | hard | `[districts].include` (existing) |
| ≥ 70 m², ≥ 3 rooms | hard | `[size]` (existing) |
| ≤ € 500 000 | hard | `[budget].price_hard_cap`, target `max_price` (new, buy mode) |
| Floor ≥ 3 | must-have | `[musthave].min_floor = 3` — drop only when the floor is *explicitly* lower; unknown / Dachgeschoss kept and flagged |
| Outdoor space | must-have | `[musthave].outdoor` (existing) |
| Energy class A/B | soft, strong | `[preferences].energy_class = ["A", "B"]`; always reported; scored, not dropped (see Decisions) |
| Kitchen-living layout, view, condition vs price | soft | free-text `[preferences].notes`, scored by Claude from floor plan, photos, description |

## Design

### 1. Mode switch in `criteria.toml`

```toml
[search]
mode = "buy"            # "rent" (default when absent) | "buy"
```

Rent profiles without `[search]` keep working unchanged. `[budget]` carries either the
rent keys (`max_rent_kalt`, `rent_hard_cap`) or the buy keys (`max_price`,
`price_hard_cap`). The loader picks the pair matching the mode and exposes them to the
rest of the code under one name: `Criteria.max_price` / `Criteria.price_hard_cap`, plus
`Criteria.mode`. A profile whose `[budget]` lacks the keys for its mode fails at load
with a clear message naming the missing keys. `[timing]` and `[furnished]` are ignored
in buy mode (loader still accepts them).

New optional keys:

```toml
[musthave]
min_floor = 3           # 0 = any. Drop only when floor is explicitly below.

[preferences]
energy_class = ["A", "B"]   # soft: preferred HWB classes; [] = don't care
notes = """
free text — the user's own words; the search skill scores against it verbatim
"""

[email]
to = ["friend@example.com"]
cc = ["me@example.com"]
```

`criteria.example.toml` documents every key, with both budget variants shown and one
commented out. `.env.example` (restored) documents SMTP.

### 2. Model: price, floor, energy, project flag

`Listing.rent` → `price`, `rent_kind` → `price_kind` with values `kalt | warm | kauf |
unknown`. Buy-mode sources set `price_kind = "kauf"`. New fields:

- `price_per_m2: float | None` — computed in `run_search` when both inputs exist.
- `floor_number: int | None` — derived from the `floor` string by a new
  `wohnung/floors.py::parse_floor()`: `"3"`, `"3. Stock"`, `"3. OG"`, `"3. Geschoss"`,
  `"3. Etage"` → 3; `EG`, `Erdgeschoss`, `Parterre`, `Hochparterre` → 0; `DG`,
  `Dachgeschoss` and anything else → `None` (kept and flagged, the string stays visible).
- `energy_class: str` — `"A"`…`"G"` or `""`; `hwb: float | None` (kWh/m²a).
- `is_project: bool` — developer/Bauträger listing whose figures are ranges; `price` is
  then the *from* price and `size_m2` may be `None`.

State meta keeps being written as `{district, rooms, size_m2, price}`; the reader
accepts the legacy `rent` key so existing `seen.json` records still dedup.

### 3. Filters and dedup

`hard_filter` compares `price` against `price_hard_cap` (same code path both modes) and
adds: `if c.min_floor and l.floor_number is not None and l.floor_number < c.min_floor:
drop`. Dedup fingerprint rounds price to the nearest 10 in rent mode and nearest 1 000
in buy mode (`fingerprint_from` gets a `mode` argument; `State` recomputes with the
configured mode).

### 4. Sources

Each client holds `SEARCH_URLS = {"rent": ..., "buy": ...}` and takes `mode` in its
constructor (`build_sources(fetcher, mode)`):

| Source | Buy URL | Parser status (verified 2026-09-14) |
|---|---|---|
| willhaben | `/iad/immobilien/eigentumswohnung/wien` | Parser already falls back to `PRICE`; `FLOOR` attribute exists. Live pages 403 to plain HTTP (rent too) — fixture must be captured via browser. |
| immoscout | `/regional/wien/wien/wohnung-kaufen` (+ `/seite-N`) | Works, but pages 1–2 are 100 % `DEVELOPER_PREMIUM` hits with area ranges, which the parser currently skips. Change: keep hits with a price but no area, mark `is_project`. Detail JSON exposes `floor`, `floorLabel`, `finalEnergyDemandClass`, `yearOfConstruction` (often null) → extract in `enrich`. |
| derStandard | `/suche/wien/kaufen-wohnung` | 403 to plain HTTP (rent too). Fixture via browser. |
| immowelt | `/liste/wien/wohnungen/kaufen` | Works: 32 cards parsed, price and `N. Geschoss` in the card title → floor from title. Detail pages 403 → no energy class from immowelt. |

Energy class extraction is best-effort text/JSON sniffing per source (`Energieklasse
A`, `HWB-Klasse B`, `HWB 45 kWh`); willhaben's detail attributes are checked once a
fixture exists. Missing → `""`, never a drop.

### 5. Search skill (`wohnung-search`)

- Reads `[search].mode` and branches the rubric. Rent rubric unchanged.
- Buy rubric, roughly in weight order: price per m² versus the district's typical
  range; energy class versus `[preferences].energy_class`; floor (≥ min, higher and
  view-facing better); outdoor; layout from floor plan (kitchen-living combined or
  clearly non-load-bearing partitions; bath/WC adjacency); condition from photos and
  description with the "renovation only if the price reflects it" rule; Betriebskosten
  and Rücklage if stated; Altbau vs Neubau; provisionsfrei; `is_project` listings are
  reported in their own short section with the from-price and a note that units vary.
- Report adds, per listing: price, €/m², floor, energy class (or "unknown"), and in
  the header a one-line reminder that purchase side costs are roughly 10 % (Grunderwerb-
  steuer 3.5 %, Eintragung 1.1 %, Notar, and ~3.6 % Provision unless provisionsfrei).
- `[preferences].notes` is quoted into the scoring step as the user's own priorities.
- Final step: if `[email].to` is set and there is at least one new listing, run
  `uv run wohnung pdf …` (when pandoc exists) then `uv run wohnung email …`. On failure,
  say so in the summary; never swallow it.

### 6. Email (restored from history commit 3dad2cd, generalized)

- `wohnung/mailer.py`: SMTP via `smtplib`, credentials from `.env` through
  `python-dotenv` (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
  `DEFAULT_FROM_EMAIL`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`). Recipients from
  `[email].to/cc` in `criteria.toml`, overridable with `--to/--cc`.
- `uv run wohnung email <report.md|.pdf> [--verify]`. Given a `.md`, it sends the
  markdown converted to a simple HTML body (links become anchors) and attaches the
  sibling `.pdf` if it exists. `--verify` only logs in.
- `.gitignore` gains `.env`, `.env.*`, `!.env.example`.
- README: the privacy section changes from "no email" to "email only if you configure
  `[email]`; credentials in `.env`, gitignored".

### 7. Setup skill

Interview asks mode first, then the budget question matching the mode, then
`min_floor`, energy class preference, free-text notes ("paste your wish list"), and
email recipients plus a pointer to `.env.example`. Existing questions otherwise
unchanged; `[timing]`/`[furnished]` are skipped in buy mode.

### 8. Tests (offline, fixtures)

- `test_config.py`: rent profile without `[search]` loads as rent; buy profile loads
  buy keys; missing budget keys → clear error; `min_floor`, `energy_class`, `notes`,
  `[email]` round-trip.
- `test_core.py`: `hard_filter` on `price_hard_cap` and `min_floor` (explicit-lower
  drops, `None` keeps); `parse_floor` table; fingerprint rounding per mode; `State`
  reading legacy `rent` meta.
- Parsers: new fixtures `immoscout_buy_search.html`, `immoscout_buy_detail.html`,
  `immowelt_buy_search.html` (captured today), `willhaben_buy_search.html` and
  `derstandard_buy_search.html` (captured via browser during implementation).
  Assertions on price, `price_kind == "kauf"`, floor, `is_project`.
- `test_mailer.py`: message assembly (recipients, subject, attachment) with a fake
  SMTP; no network.

## Decisions and open risks

1. **Energy class is soft, not hard.** In districts 1–9 at ≤ € 500 000 and ≥ 70 m²,
   class A/B is essentially Neubau, which is rare at that price; the friend also said
   light renovation is fine, which points at Altbau (typically C–D). A hard drop plus
   patchy extraction would empty the report. Flip by moving the list to
   `[musthave].energy_class` if the first reports say otherwise. (Not implemented as a
   hard key now — YAGNI until asked.)
2. **Developer projects on immoscout** dominate the buy listings. Keeping them with a
   from-price and an `is_project` flag beats dropping them, since Neubau is where A/B
   energy classes live.
3. **willhaben and derStandard 403** on plain HTTP, rent and buy alike. The skill's
   Playwright fallback covers it manually; unattended runs will miss those two sources
   until that is solved. Follow-up spike: `curl_cffi` browser impersonation in
   `Fetcher`.
4. **State is shared** between modes. Ids are source-prefixed and distinct; fingerprints
   cannot collide across modes because prices differ by two orders of magnitude.
