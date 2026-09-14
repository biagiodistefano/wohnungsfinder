---
description: Search Vienna portals for new apartments (rent or buy, per criteria.toml) matching the configured profile, produce a ranked report, and email it if configured
---

Invoke the `wohnung-search` skill: run a fresh apartment search across the configured
portals in the configured mode (rent or buy), evaluate the new listings (including their
photos), write a ranked report, and email it when `[email].to` is set in `criteria.toml`.

Optional argument: a number of pages to sweep per source (default 3). Example: `/wohnung-search 5`.
