---
name: wohnung-search
description: Run a fresh Vienna apartment search, evaluate new listings (including their photos), and write a ranked report. Use when the user asks to search/check for new apartments, runs /wohnung-search, or asks for the latest Wohnung report.
---

# Vienna apartment search & evaluation

This project hunts for a rental apartment in Vienna. A Python tool (`wohnung`) fetches
listings, dedups against local state, downloads photos, and computes U-Bahn proximity.
**You** then look at the photos, score against the user's profile, and write the ranked
report. The tool does the fetching; the judgment is yours.

## The search profile

The profile lives in **`criteria.toml`** (personal, gitignored). **Read it before every
search** — budget, size, districts, must-haves, furnished policy, move-in timing, and
the report language all come from there. Never assume values from a previous session.

If `criteria.toml` doesn't exist, stop and tell the user to run `/setup` first.

Semantics to keep in mind:

- **Hard filters** (rent cap, size, rooms, districts) are already applied by the tool.
- **Must-haves** (`[musthave]`) hard-drop only when a listing *explicitly* lacks them;
  when unknown they're kept and flagged — verifying those flags is part of your job.
- The headline rent figure may be warm rather than kalt — flag uncertainty.

## Steps

1. **Run the search.** From the repo root:
   ```bash
   uv run wohnung search --max-pages 3
   ```
   (Use the page count the user gave, e.g. `/wohnung-search 5` → `--max-pages 5`. Drop
   `--no-images` so photos download.) The command prints `new / excluded / duplicates / errors`
   counts plus `(known before: N)` — the number of ids already in the dedup state.
   **If you see a `!! ... state looks WIPED` warning** (or `known before: 0` when this isn't the
   first-ever run), the dedup state was lost and *every* listing will resurface as "new". Stop and
   run `uv run wohnung reindex` to rebuild state from past reports, then re-run the search.

2. **Handle blocked sources.** If the output lists a source under errors with a 403/block,
   fetch that portal's search URL with the **Playwright browser MCP**
   (`browser_navigate` then `browser_snapshot` / get HTML), save the HTML, and run the
   matching `parse_search` on it in a quick `uv run python -c ...` to recover listings.
   Note the fallback in the report. Source URLs:
   - willhaben: `https://www.willhaben.at/iad/immobilien/mietwohnungen/wien`
   - immoscout: `https://www.immobilienscout24.at/regional/wien/wien/wohnung-mieten`
   - derstandard: `https://immobilien.derstandard.at/suche/wien/mieten-wohnung`

3. **Read `reports/.last_run.json`.** It has `new_listings` (full data + `local_images`),
   `excluded` (id/url/reason), `duplicates` (cross-source/cross-run dupes already merged away),
   `source_errors`, and `state_known_before` / `state_warning` (dedup-state health). If
   `new_listings` is empty, say so and stop after a short note (still mention excluded/duplicate
   counts and any errors).
   - **Cross-run sanity check:** if `state_warning` is set (or `state_known_before` is 0 outside a
     first run), the state was wiped — `reindex` first (see step 1) rather than reporting a flood of
     false "new" listings. As a lighter check, compare `new_listings` URLs against the **most recent
     previous `reports/*.md`**; if listings you already reported reappear as "new", that's a dedup
     problem worth flagging (and usually a wiped/again-lost state).

4. **View the photos.** For each new listing, Read the images in `images/<id>/` (and any
   floor plan). Judge: brightness, renovation/condition, sensible layout, and — if a floor
   plan is present — **whether toilet and bathroom are combined/adjacent (bonus) or on
   opposite ends (penalty)**.

5. **Score the soft preferences** (weight roughly in this order):
   - **U-Bahn proximity (heavy):** use `ubahn_distance_m` — closer to a U-line is much better.
     If it's null, say "U-Bahn distance unknown".
   - **Move-in timing** (only if `[timing].lease_ends` is set in `criteria.toml`): score
     `available_from` against the configured anchors. The `ideal_move_in` date is the peak;
     dates giving between `overlap_min_weeks` and `overlap_max_months` of overlap with the
     lease end are good-to-acceptable (closer to ideal = better); outside that window = mild
     penalty. `available_from` is best-effort (a date, "sofort", or empty) — if empty, read
     the description for "verfügbar/bezug ab …" and note uncertainty; "sofort"/now counts as
     very early (mild penalty if that's outside the window, but often negotiable — say so).
   - **Bath/WC adjacency** (from floor plan / description).
   - **Provisionsfrei** (`provisionsfrei: true`) preferred over agency listings.
   - **Home-office / extra room** beyond the minimum.
   - **Furnished** (only if `[furnished].penalize_furnished` is true): an apartment let
     **fully furnished / möbliert** (vollmöbliert, komplett möbliert) scores *negatively*.
     **Judge this from the description and structured metadata, NOT the photos:** furniture in
     photos is often just the current tenant's belongings while they still live there, so a
     furnished-*looking* photo is not evidence. Penalize only when the **text** says it's let
     furnished (title/description keywords like "möbliert", "vollmöbliert", "fully furnished",
     "inkl. Möbel"). When the text is silent, assume unfurnished (no penalty). A fitted
     kitchen (Einbauküche) is normal and is *not* a furnished penalty.
   - **Lower rent** vs the configured `max_rent_kalt`.
   - **Photo quality** (condition, light, layout).
   - **Flag** any listing where `has_elevator` or `has_outdoor` is `null` (unconfirmed — verify
     from the description/photos or note it).

6. **Write `reports/YYYY-MM-DD-HHMM.md`** — a ranked shortlist (best first), written in the
   **language configured in `criteria.toml` `[report].language`** (portal-specific German terms
   like Zimmer, kalt, provisionsfrei, Altbau can stay untranslated). For each listing:
   title, district, rent (note kalt/warm uncertainty), size, rooms, nearest U-Bahn + distance,
   elevator/outdoor status (confirmed vs unknown), bath/WC note, a 1–2 line photo assessment,
   a score/verdict, and the listing URL. Add an **Excluded** section (url + reason) so nothing
   silently vanishes, and a **Source status** line noting any `source_errors`/fallbacks, how
   many cross-source `duplicates` were merged away, and **known listings in state: N**
   (`state_known_before`) so a future state-wipe is visible in the report itself. For geocoded
   sources (derStandard, immowelt),
   the U-Bahn distance is an address estimate — note that; if a listing has no `ubahn_distance_m`
   at all, the geocode missed, so say "U-Bahn unknown".
   - **Links:** use the **exact `url` field** from each listing in `.last_run.json` verbatim — never
     hand-write or shorten a URL, and never reuse a base/category URL. Double-check the id in the
     link matches the listing you're describing. Write every link as a **new-tab HTML anchor**, not a
     markdown link: `<a href="URL" target="_blank" rel="noopener">URL</a>`.
   - **Sanity-check coordinates:** if a listing's `district`/`address` is clearly far from its
     `nearest_ubahn` (common for off-plan/new-build ads with a placeholder coordinate), don't trust
     `ubahn_distance_m` — say the coordinate looks wrong and estimate transit from the address instead.

   **Reports are local-only artifacts.** The whole `reports/` directory is gitignored —
   never commit, push, or otherwise publish a report; it contains the user's personal
   search activity.

7. **Optionally generate a PDF** — only if the user asked for one:
   ```bash
   uv run wohnung pdf reports/<YYYY-MM-DD-HHMM>.md
   ```
   This writes `reports/<same-name>.pdf` (also gitignored). If pandoc isn't installed it
   errors clearly; mention that to the user rather than failing silently.

8. **Summarize inline** to the user (in the report language): how many new listings, and
   the top 3 with one line each.

## Notes

- Rent kalt vs warm is **not always distinguishable** from portal data — always show the figure
  and flag uncertainty rather than asserting it's kalt. If many good listings are excluded on
  "rent over cap", suggest the user raise `rent_hard_cap` in `criteria.toml`.
- When the user reacts to a listing, record it: `uv run wohnung mark <id> interested|rejected|contacted`.
- To refresh U-Bahn station coordinates: `uv run python scripts/build_ubahn.py`.
- Editing the profile: re-run `/setup` or edit `criteria.toml` directly. State (dedup) lives
  in `state/seen.json`.
- **Never `rm state/seen.json`** (or wipe `state/`) without a backup — losing it makes every listing
  resurface as "new". The tool snapshots `state/seen.json.bak` on each run and writes atomically, and
  `uv run wohnung reindex` rebuilds state from past `reports/*.md` + `.last_run.json` if it's ever lost.
