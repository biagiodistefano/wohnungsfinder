from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wohnung.config import load_criteria
from wohnung.dedup import fingerprint
from wohnung.fetch import Fetcher
from wohnung.filters import hard_filter
from wohnung.geocode import Geocoder, query_for
from wohnung.images import download_images
from wohnung.state import State
from wohnung.ubahn import nearest_ubahn

ROOT = Path(__file__).resolve().parent.parent


_SOURCE_SPECS = [
    ("wohnung.sources.willhaben_client", "WillhabenSource"),
    ("wohnung.sources.immoscout_client", "ImmoScoutSource"),
    ("wohnung.sources.derstandard_client", "DerStandardSource"),
    ("wohnung.sources.immowelt_client", "ImmoweltSource"),
]


def build_sources(fetcher: Fetcher, mode: str = "rent") -> list:
    """Instantiate each configured source. A source module that is missing or fails
    to import is skipped with a warning rather than aborting the run."""
    import importlib

    sources = []
    for module_name, class_name in _SOURCE_SPECS:
        try:
            mod = importlib.import_module(module_name)
            sources.append(getattr(mod, class_name)(fetcher, mode=mode))
        except Exception as e:  # noqa: BLE001
            print(f"  ! skipping {class_name}: {type(e).__name__}: {e}", file=sys.stderr)
    return sources


def run_search(root: Path = ROOT, max_pages: int = 3, download: bool = True) -> dict:
    c = load_criteria()
    state = State(root / "state" / "seen.json", mode=c.mode)
    known_before = state.count_loaded
    state_warning = None
    if state.was_wiped():
        state_warning = (
            f"state/seen.json was empty at start but a backup holds {state._backup_count()} "
            "ids — dedup state looks WIPED. Every listing will surface as 'new'. "
            "Recover with: uv run wohnung reindex (rebuilds from past reports)."
        )
        print(f"  !! {state_warning}", file=sys.stderr)
    geocoder = Geocoder(root / "state" / "geocode_cache.json", contact=c.geocode_contact)
    fetcher = Fetcher()
    new_listings, excluded, duplicates, source_errors = [], [], [], []
    projects = []  # developer/Bauträger projects: ranges, no price; reported separately
    seen_fps: set[str] = set()  # fingerprints surfaced earlier in THIS run

    def _meta(l):  # fingerprint inputs, persisted so the dedup key survives/recomputes
        return {"district": l.district, "rooms": l.rooms, "size_m2": l.size_m2, "price": l.price}

    for src in build_sources(fetcher, c.mode):
        try:
            found = src.search(max_pages=max_pages)
        except Exception as e:  # a source failing must not abort the whole run
            source_errors.append({"source": src.name, "error": f"{type(e).__name__}: {e}"})
            continue

        for l in found:
            if not state.is_new(l.id):
                continue
            ok, reason = hard_filter(l, c)  # cheap pre-filter on summary fields
            if not ok:
                excluded.append({"id": l.id, "url": l.url, "reason": reason})
                state.record(l.id, source=l.source, url=l.url, status="excluded")
                continue
            if l.is_project:
                # No concrete unit to evaluate: skip detail fetch, photos, and dedup.
                state.record(l.id, source=l.source, url=l.url, status="project")
                projects.append(l)
                continue
            try:
                src.enrich(l)
            except Exception as e:
                source_errors.append(
                    {"source": src.name, "id": l.id, "error": f"{type(e).__name__}: {e}"}
                )
            ok, reason = hard_filter(l, c)  # re-check with enriched fields
            if not ok:
                excluded.append({"id": l.id, "url": l.url, "reason": reason})
                state.record(l.id, source=l.source, url=l.url, status="excluded")
                continue

            # Cross-source / cross-run dedup: the same flat cross-posted to several
            # portals collapses to one. No fingerprint (missing fields) => never merged.
            fp = fingerprint(l, mode=c.mode)
            if fp and (state.has_fingerprint(fp) or fp in seen_fps):
                duplicates.append({"id": l.id, "url": l.url, "fingerprint": fp})
                state.record(
                    l.id, source=l.source, url=l.url, status="duplicate",
                    fingerprint=fp, meta=_meta(l),
                )
                continue
            if fp:
                seen_fps.add(fp)

            # Backfill coordinates by geocoding when the source has none (immowelt,
            # derStandard). Strictly best-effort: failure leaves U-Bahn unknown.
            if l.coordinates is None:
                try:
                    coords = geocoder.lookup(query_for(l))
                    if coords:
                        l.coordinates = coords
                except Exception:
                    pass
            if l.coordinates:
                l.nearest_ubahn, l.ubahn_distance_m = nearest_ubahn(*l.coordinates)
            if download:
                download_images(l, fetcher, root / "images")
            state.record(
                l.id, source=l.source, url=l.url, status="new",
                fingerprint=fp, meta=_meta(l),
            )
            new_listings.append(l)

    fetcher.close()
    out = {
        "new_listings": [l.to_json() for l in new_listings],
        "projects": [l.to_json() for l in projects],
        "excluded": excluded,
        "duplicates": duplicates,
        "source_errors": source_errors,
        "state_known_before": known_before,  # ids in seen.json at run start (0 => fresh/wiped)
        "state_warning": state_warning,  # set when the dedup state looks wiped
    }
    rpt = root / "reports"
    rpt.mkdir(parents=True, exist_ok=True)
    (rpt / ".last_run.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out


def _current_mode() -> str:
    """Search mode from criteria.toml, or "rent" when there is no profile yet."""
    try:
        return load_criteria().mode
    except SystemExit:
        return "rent"


def make_pdf(md_path, out_path=None) -> Path:
    """Render a markdown report to PDF via pandoc (weasyprint engine preferred).
    PDFs are gitignored — this is a local/shareable artifact, not committed."""
    import shutil
    import subprocess

    md = Path(md_path)
    if not md.exists():
        raise FileNotFoundError(md)
    out = Path(out_path) if out_path else md.with_suffix(".pdf")
    if not shutil.which("pandoc"):
        raise RuntimeError("pandoc not found — install it (brew install pandoc) to generate PDFs")
    cmd = ["pandoc", str(md), "-o", str(out)]
    for engine in ("weasyprint", "wkhtmltopdf"):
        if shutil.which(engine):
            cmd.append(f"--pdf-engine={engine}")
            break
    subprocess.run(cmd, check=True)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(prog="wohnung")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="fetch new listings and write reports/.last_run.json")
    s.add_argument("--max-pages", type=int, default=3)
    s.add_argument("--no-images", action="store_true")
    m = sub.add_parser("mark", help="set a listing's status (interested/rejected/contacted)")
    m.add_argument("id")
    m.add_argument("status")
    sub.add_parser("reindex", help="rebuild seen.json from past reports (recover lost dedup state)")
    pdf = sub.add_parser("pdf", help="render a markdown report to PDF (gitignored)")
    pdf.add_argument("md", help="path to the report .md")
    pdf.add_argument("--out", help="output .pdf path (default: same name, .pdf)")
    em = sub.add_parser(
        "email", help="email a report (.md or .pdf) to the recipients in criteria.toml [email]"
    )
    em.add_argument(
        "report", nargs="?",
        help="path to the report .md (sibling .pdf attached if present) or .pdf",
    )
    em.add_argument("--to", action="append", help="override To recipient(s)")
    em.add_argument("--cc", action="append", help="override Cc recipient(s)")
    em.add_argument("--verify", action="store_true", help="only test SMTP login, don't send")
    args = p.parse_args(argv)

    if args.cmd == "pdf":
        out = make_pdf(args.md, args.out)
        print(f"wrote {out}")
        return

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

    if args.cmd == "search":
        out = run_search(max_pages=args.max_pages, download=not args.no_images)
        print(
            f"new: {len(out['new_listings'])}  "
            f"projects: {len(out['projects'])}  "
            f"excluded: {len(out['excluded'])}  "
            f"duplicates: {len(out['duplicates'])}  "
            f"errors: {len(out['source_errors'])}  "
            f"(known before: {out['state_known_before']})"
        )
        if out.get("state_warning"):
            print(f"  !! {out['state_warning']}")
        for e in out["source_errors"]:
            print(f"  ! {e}")
    elif args.cmd == "mark":
        State(ROOT / "state" / "seen.json", mode=_current_mode()).mark(args.id, args.status)
        print(f"{args.id} -> {args.status}")
    elif args.cmd == "reindex":
        from wohnung.recover import reindex

        r = reindex(ROOT, mode=_current_mode())
        print(f"reindexed: added {r['added']} ids from {r['scanned']} found "
              f"(state now {r['total']})")


if __name__ == "__main__":
    main(sys.argv[1:])
