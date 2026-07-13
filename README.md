# Wohnungsfinder

An AI-assisted apartment hunt for **Vienna**, built to run inside
[Claude Code](https://claude.com/claude-code). A small, deliberately "dumb and
reliable" Python tool fetches listings from the major Austrian rental portals,
dedups them against local state, downloads photos, and computes U-Bahn
proximity. Claude then does what actually needs judgment: it looks at the
photos, scores each listing against your personal profile, and writes a ranked
report — in your language.

It found its author a flat; now it's yours. MIT licensed.

> **If you are Claude** (or another coding agent) reading this inside the repo:
> the operating manuals are the skills. `.claude/skills/setup/SKILL.md` is the
> onboarding interview; `.claude/skills/wohnung-search/SKILL.md` is the search
> procedure and defines your responsibilities (photo evaluation, soft scoring,
> report writing). The user's profile is `criteria.toml` — personal and
> gitignored; read it fresh every run, never hardcode its values, and never
> commit reports, state, images, or `criteria.toml`.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (`brew install uv`) and Python ≥ 3.12
(uv will fetch one if needed). Optional: `pandoc` for PDF export.

```
git clone <this repo> && cd wohnungsfinder
claude
> /setup            # guided interview: language, budget, districts, must-haves…
> /wohnung-search   # first search + ranked report
```

`/setup` writes your profile to `criteria.toml` (gitignored), runs `uv sync`,
and can optionally schedule unattended searches. `/wohnung-search N` sweeps N
pages per portal (default 3).

The Python tool also works standalone — fetching, filtering, and dedup happen
without any LLM:

```bash
uv run wohnung search --max-pages 3    # fetch + dedup + photos + reports/.last_run.json
uv run wohnung search --no-images      # skip photo download
uv run wohnung mark <id> interested    # interested | rejected | contacted
uv run wohnung reindex                 # rebuild dedup state from past reports
uv run wohnung pdf reports/<name>.md   # render a report to PDF (needs pandoc)
```

What you lose without Claude is the judgment layer: photo evaluation, soft
scoring, and the written report.

## How a search run works

1. `uv run wohnung search` fetches every configured portal, applies the **hard
   filters** from `criteria.toml` (rent cap, size, rooms, districts), merges
   cross-source duplicates, geocodes listings that lack coordinates, computes
   U-Bahn distance, downloads photos, and writes `reports/.last_run.json`.
2. Claude reads that JSON, **looks at the photos** (brightness, condition,
   layout, floor-plan details like bath/WC adjacency), scores the **soft
   preferences** (U-Bahn proximity, move-in timing, provisionsfrei, furnished
   penalty, price headroom…), and writes a ranked shortlist to
   `reports/YYYY-MM-DD-HHMM.md` — in the language set in `[report].language`.
3. Everything a run produces is **local-only** (see "Privacy model" below).

### Hard vs soft criteria

Hard filters drop a listing outright and are enforced in Python. Must-haves
(elevator, outdoor space) hard-drop **only when explicitly absent** — a listing
that doesn't mention an elevator is kept and flagged for Claude to verify.
Everything else is a soft preference, scored by Claude, because "is this a
nice, bright flat with a sane layout" is not a regex.

## Sources

| Source | How it's parsed |
|--------|-----------------|
| [willhaben.at](https://www.willhaben.at) | `__NEXT_DATA__` JSON (search summary + detail page for equipment/description/images) — native coords for U-Bahn |
| [immobilienscout24.at](https://www.immobilienscout24.at) | `window.__INITIAL_STATE__` (`reduxAsyncConnect…results.hits`) — native coords; elevator/outdoor sniffed from detail text |
| [derStandard Immobilien](https://immobilien.derstandard.at) | Server-rendered listing cards; district from the detail page. No native coords → **geocoded** |
| [immowelt.at](https://www.immowelt.at) | Server-rendered card `title` + `/expose/` URL; district/elevator/outdoor from detail page. First ~30 only (deeper pages are API-gated). No native coords → **geocoded** |

Genossenschaft/co-op (waitlist-based) sources are out of scope.

**Cross-source dedup:** the same flat is often cross-posted to several portals.
Listings are fingerprinted by `(district, rooms, ~size, ~price)`; a fingerprint
already seen (this run or a previous one) is recorded as a `duplicate` and not
re-shown. Listings missing those fields get no fingerprint and are always kept.

**Geocoding:** sources without coordinates are geocoded via OpenStreetMap
Nominatim (cached in `state/geocode_cache.json`, ≤ 1 req/s, contact info from
`[geocode].contact` per OSM policy). Strictly best-effort — a geocode miss just
leaves U-Bahn unknown; it never blocks or drops a listing.

## Privacy model — what's committed vs local

The repo is meant to be publishable; your search is not. Committed: code,
tests + fixtures, skills, `criteria.example.toml`, this README. Everything
personal is gitignored and stays on your machine:

| Local-only (gitignored) | What it is |
|-------------------------|------------|
| `criteria.toml` | your profile: budget, districts, timing, language, contact |
| `reports/` | ranked reports + `.last_run.json` (your search activity) |
| `state/` | dedup memory (`seen.json`) + geocode cache |
| `images/` | downloaded listing photos |
| `logs/` | scheduled-run logs |

Nothing is sent anywhere: no email, no telemetry, no third-party services
beyond the portals themselves and Nominatim.

## Scheduled runs (macOS, optional)

A LaunchAgent can run `/wohnung-search` unattended (e.g. 09:00 and 18:00) via
`claude -p`, so photo evaluation and reports draw on a Claude subscription
rather than API credits. `/setup` offers to install it; the pieces are
`scripts/wohnung-cron.sh` and the template `scripts/local.wohnungsfinder.search.plist`
(replace `__REPO__` with your checkout path — launchd doesn't expand variables).

Heads-up: unattended runs use `--dangerously-skip-permissions`, since Claude
can't pause to approve tools. Read `scripts/wohnung-cron.sh` and be comfortable
with that trade-off before enabling. Only runs while the Mac is awake — a
missed slot fires shortly after wake; a powered-off Mac skips it.

## Repo layout

- `wohnung/` — the Python package; `wohnung/sources/` has one module per portal
  (`*_client.py` does HTTP, the sibling module parses)
- `wohnung/data/ubahn_stations.json` — U-Bahn coordinates, regenerable via
  `scripts/build_ubahn.py` from Wiener Linien open data
- `.claude/skills/` — the two skills (`setup`, `wohnung-search`);
  `.claude/commands/` — their slash commands
- `criteria.example.toml` — annotated profile template
- `tests/` — parser tests against saved HTML fixtures (offline, no network)

## Maintenance

Portals change their markup periodically; each source is isolated in its own
module so a breakage only affects that one source (the run continues and logs
the failure rather than aborting). When a parser stops returning listings,
re-capture a fixture under `tests/fixtures/` and fix that source's
`parse_search`. If a portal starts bot-blocking plain HTTP (403), the
`wohnung-search` skill falls back to the Playwright browser MCP for that source.

```bash
uv sync          # install deps
uv run pytest    # parser tests run against saved fixtures (offline)
```

### Caveats

- **Kalt vs warm rent** is not always distinguishable from portal data. The
  tool filters on the headline figure and flags uncertainty; if good listings
  get excluded on "rent over cap", raise `rent_hard_cap` in `criteria.toml`.
- Scrapers are best-effort and Vienna-specific; adapting to another city means
  new source modules, district logic, and transit data.

## License

[MIT](LICENSE).
