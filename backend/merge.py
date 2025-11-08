from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable, List, Tuple

from .models import Competition, Fixture
from .normalise import map_irish_tokens, norm_text
from .utils import iso_z, london_weekend_for, slugify


SOURCE_PRIORITY = {"gaa_gms": 3, "clubzap": 2, "ics": 1, "scraper": 0}


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _best_time_bucket(hhmm: str) -> int:
    # Round to nearest 5 minutes
    mins = _minutes(hhmm)
    return round(mins / 5) * 5


def _norm_team(s: str) -> str:
    return norm_text(map_irish_tokens(s))


def popularity_score(name: str) -> int:
    t = name.lower()
    score = 0
    if "all-ireland" in t:
        score += 100
    if any(x in t for x in ["ulster", "munster", "leinster", "connacht", "provincial"]):
        score += 80
    if any(x in t for x in ["national league", "nfl", "nhl"]):
        score += 70
    if "senior championship" in t:
        score += 60
    if "intermediate" in t:
        score += 50
    if "junior" in t:
        score += 40
    if any(x in t for x in ["division", "league"]):
        score += 30
    if "friendly" in t:
        score += 10
    return score


def _completeness_points(f: Fixture) -> int:
    pts = 0
    if f.venue:
        pts += 1
    if f.status == "FT":
        pts += 3
    if f.score:
        pts += 2
    return pts


def dedupe(fixtures: Iterable[Fixture]) -> List[Fixture]:
    by_key: dict[Tuple[str, int, str, str, str], List[Fixture]] = defaultdict(list)
    for f in fixtures:
        comp_slug = slugify(f.competition)
        key = (f.date, _best_time_bucket(f.time), _norm_team(f.home), _norm_team(f.away), comp_slug)
        by_key[key].append(f)

    merged: List[Fixture] = []
    for _key, group in by_key.items():
        # Prefer higher source priority, then completeness, then newest updated_at
        group.sort(
            key=lambda x: (
                SOURCE_PRIORITY.get(x.source, -1),
                _completeness_points(x),
                x.updated_at,
            ),
            reverse=True,
        )
        chosen = group[0]
        merged.append(chosen)
    # sort chronologically
    merged.sort(key=lambda f: (f.date, f.time))
    return merged


def collapse_future_duplicates(fixtures: Iterable[Fixture]) -> List[Fixture]:
    """Collapse duplicate future fixtures by team pair, keeping the earliest.

    Upstream pages can sometimes publish the same pairing twice with slightly
    different competition strings (e.g. missing spaces) or re-posted dates.
    We treat duplicates as "same home+away" and keep the soonest upcoming one.

    Results (FT) are never collapsed.
    """
    groups: dict[Tuple[str, str], List[Fixture]] = defaultdict(list)
    for f in fixtures:
        if f.status == "FT":
            continue
        key = (_norm_team(f.home), _norm_team(f.away))
        groups[key].append(f)

    keep_ids: set[str] = set()
    for items in groups.values():
        if len(items) == 1:
            keep_ids.add(items[0].id)
            continue
        items_sorted = sorted(items, key=lambda x: (x.date, x.time))
        keep_ids.add(items_sorted[0].id)

    out: List[Fixture] = []
    for f in fixtures:
        key = (_norm_team(f.home), _norm_team(f.away))
        if f.status == "FT" or (key in groups and f.id in keep_ids) or (key not in groups):
            out.append(f)
    out.sort(key=lambda f: (f.date, f.time))
    return out


def competitions_from_fixtures(fixtures: Iterable[Fixture]) -> List[Competition]:
    comps: dict[str, List[Fixture]] = defaultdict(list)
    for f in fixtures:
        comps[f.competition].append(f)
    out: List[Competition] = []
    for name, items in comps.items():
        slug = slugify(name)
        pop = popularity_score(name)
        items_sorted = sorted(items, key=lambda x: (x.date, x.time))
        first = items_sorted[0]
        # Build ISO kick-off in UTC from local date+time (assume :00 seconds)
        dt = datetime.fromisoformat(f"{first.date}T{first.time}:00")
        first_iso = iso_z(dt)
        out.append(
            Competition(
                name=name,
                slug=slug,
                popularity=pop,
                match_count=len(items),
                first_kickoff=first_iso,
            )
        )
    out.sort(key=lambda c: (-c.popularity, -c.match_count, c.first_kickoff))
    return out


def weekend_top_competitions(fixtures: Iterable[Fixture], today: datetime) -> List[Competition]:
    sat, sun = london_weekend_for(today.date())
    weekend = [f for f in fixtures if sat.isoformat() <= f.date <= sun.isoformat()]
    comps = competitions_from_fixtures(weekend)
    return comps[:3]
