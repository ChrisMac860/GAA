from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timedelta
from typing import List

from .adapters import fetch_clubzap, fetch_gms, fetch_ics, fetch_scraper
from .merge import competitions_from_fixtures, dedupe, collapse_future_duplicates
from .models import Fixture
from .normalise import build_search_index, is_placeholder_team
from .utils import ensure_dir, iso_z, write_json


ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "backend" / ".cache"
PUBLIC = ROOT / "public" / "data"


def load_config() -> dict:
    cfg_path = ROOT / "backend" / "config.yaml"
    import yaml  # type: ignore

    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def fetch_cmd() -> None:
    cfg = load_config()
    ensure_dir(CACHE)

    all_fixtures: List[Fixture] = []

    for name, fn in (
        ("gaa_gms", fetch_gms),
        ("clubzap", fetch_clubzap),
        ("ics", fetch_ics),
        ("scraper", fetch_scraper),
    ):
        try:
            items = fn(cfg)
            all_fixtures.extend(items)
            (CACHE / f"{name}_raw.json").write_text(
                json.dumps([i.model_dump() for i in items], indent=2), encoding="utf-8"
            )
        except Exception as e:
            (CACHE / f"{name}_error.log").write_text(str(e), encoding="utf-8")

    # Write combined cache too
    (CACHE / "combined_raw.json").write_text(
        json.dumps([i.model_dump() for i in all_fixtures], indent=2), encoding="utf-8"
    )


def build_cmd() -> None:
    cfg = load_config()
    ensure_dir(PUBLIC)

    days_forward = int(cfg.get("days_forward", 14))
    days_back = int(cfg.get("days_back", 7))
    results_days_back = int(cfg.get("results_days_back", days_back))
    scraper_days_forward = int(cfg.get("scraper_days_forward", days_forward))

    # Load combined cache or seeds via adapters
    combined = CACHE / "combined_raw.json"
    if combined.exists():
        raw = json.loads(combined.read_text(encoding="utf-8"))
        fixtures = [Fixture(**x) for x in raw]
    else:
        # no cache yet; fetch locally from seeds
        fetch_cmd()
        raw = json.loads((CACHE / "combined_raw.json").read_text(encoding="utf-8"))
        fixtures = [Fixture(**x) for x in raw]

    # Normalise search index
    build_search_index(fixtures)

    # Merge & dedupe
    merged = dedupe(fixtures)

    # Drop placeholder matchups (e.g., "Winner of ...", group placeholders)
    merged = [f for f in merged if not (is_placeholder_team(f.home) or is_placeholder_team(f.away))]

    # Collapse accidental duplicates on different dates within same competition
    merged = collapse_future_duplicates(merged)

    # Windowing
    now = datetime.utcnow()
    start_results = (now - timedelta(days=results_days_back)).date().isoformat()
    end_results = now.date().isoformat()
    start_fixtures = now.date().isoformat()
    end_fixtures = (now + timedelta(days=days_forward)).date().isoformat()
    end_fixtures_scraper = (now + timedelta(days=scraper_days_forward)).date().isoformat()

    upcoming = [
        f for f in merged
        if f.date >= start_fixtures and (
            (f.date <= end_fixtures) or (f.source == "scraper" and f.date <= end_fixtures_scraper)
        )
    ]
    recent = [f for f in merged if start_results <= f.date <= end_results and (f.status == "FT" or (f.score or "").strip())]
    if not recent:
        # Fallback: show latest FT results within a broader window to avoid empty UI
        fallback_days = int(cfg.get("results_fallback_days", 365))
        cutoff = (now - timedelta(days=fallback_days)).date().isoformat()
        candidates = [f for f in merged if f.status == "FT" and f.date >= cutoff]
        candidates.sort(key=lambda x: (x.date, x.time), reverse=True)
        recent = candidates[:50]

    # Competitions from upcoming window
    competitions = competitions_from_fixtures(upcoming)

    preserve_on_empty = bool(cfg.get("preserve_on_empty", True))

    def maybe_write(path, new_list):
        if preserve_on_empty and (not new_list):
            # keep existing file if present
            if path.exists():
                return
        write_json(path, new_list)

    maybe_write(PUBLIC / "fixtures.json", [f.model_dump() for f in upcoming])
    maybe_write(PUBLIC / "results.json", [f.model_dump() for f in recent])
    maybe_write(PUBLIC / "competitions.json", [c.model_dump() for c in competitions])


def validate_cmd() -> None:
    # Basic validation: files exist and fields non-empty
    ok = True
    for name in ("fixtures.json", "results.json", "competitions.json"):
        p = PUBLIC / name
        if not p.exists():
            print(f"missing {name}")
            ok = False
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            print(f"{name} not a list")
            ok = False
            continue
        if name != "competitions.json":
            for idx, f in enumerate(data):
                for field in ("id", "date", "time", "competition", "home", "away", "status", "source", "updated_at"):
                    if not f.get(field):
                        print(f"{name}[{idx}] missing {field}")
                        ok = False
                        break
    if not ok:
        raise SystemExit(1)
    print("ok")


def main() -> None:
    parser = argparse.ArgumentParser(prog="backend", description="GAA fixtures pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    sub.add_parser("build")
    sub.add_parser("all")
    sub.add_parser("validate")
    args = parser.parse_args()

    if args.cmd == "fetch":
        fetch_cmd()
    elif args.cmd == "build":
        build_cmd()
    elif args.cmd == "all":
        fetch_cmd()
        build_cmd()
    elif args.cmd == "validate":
        validate_cmd()


if __name__ == "__main__":
    main()
