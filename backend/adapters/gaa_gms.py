from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

import httpx
from tenacity import retry, wait_exponential, stop_after_attempt

from ..models import Fixture
from ..utils import read_env, to_london_date_time, iso_z


def _parse_jsonp(body: str) -> Any:
    # Strip callback( ... );
    start = body.find("(")
    end = body.rfind(")")
    if start != -1 and end != -1 and end > start:
        inner = body[start + 1 : end]
        return json.loads(inner)
    return json.loads(body)


@retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
def _get(client: httpx.Client, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> httpx.Response:
    return client.get(url, params=params, headers=headers, timeout=15)


def _fallback_seed() -> List[Fixture]:
    # Samples removed by request; no fallback.
    return []


def _map_open_data_item(x: dict[str, Any]) -> Optional[Fixture]:
    # Try to map flexible keys from Foireann Open Data
    def first_key(*keys: str) -> Any:
        for k in keys:
            if k in x and x[k] not in (None, ""):
                return x[k]
        return None

    fid = str(first_key("id", "fixtureId", "matchId", "uuid") or "")
    comp = first_key("competition", "competitionName", "competitionTitle") or ""
    home = first_key("homeTeam", "homeTeamName", "home") or ""
    away = first_key("awayTeam", "awayTeamName", "away") or ""
    venue = first_key("venue", "venueName")
    status_raw = (first_key("status", "state") or "scheduled").lower()
    if "postpon" in status_raw:
        status = "PP"
    elif "ft" in status_raw or "result" in status_raw or status_raw == "finished":
        status = "FT"
    else:
        status = "scheduled"

    # Time/Date: accept ISO date/datetime
    dt_iso = first_key("startDateTime", "throwIn", "kickOff", "start", "dateTime")
    date_only = first_key("date")
    time_only = first_key("time")
    date_str: str
    time_str: str
    if dt_iso:
        try:
            dt = datetime.fromisoformat(str(dt_iso).replace("Z", "+00:00"))
            date_str, time_str = to_london_date_time(dt)
        except Exception:
            return None
    elif date_only and time_only:
        try:
            dt = datetime.fromisoformat(f"{date_only}T{time_only}:00")
            date_str, time_str = to_london_date_time(dt)
        except Exception:
            return None
    else:
        return None

    # Score mapping
    score = ""
    hg = first_key("homeGoals", "home_goals")
    hp = first_key("homePoints", "home_points")
    ag = first_key("awayGoals", "away_goals")
    ap = first_key("awayPoints", "away_points")
    if all(v is not None for v in [hg, hp, ag, ap]):
        score = f"{hg}-{hp} – {ag}-{ap}"
    else:
        hs = first_key("homeScore", "home_score")
        as_ = first_key("awayScore", "away_score")
        if hs is not None and as_ is not None:
            score = f"{hs} – {as_}"

    if not (fid and comp and home and away and date_str and time_str):
        return None

    return Fixture(
        id=fid,
        date=date_str,
        time=time_str,
        competition=str(comp),
        home=str(home),
        away=str(away),
        venue=str(venue) if venue else None,
        status=status,  # type: ignore[assignment]
        score=str(score) if score else "",
        source="gaa_gms",
        updated_at=iso_z(datetime.utcnow()),
    )


def _fetch_open_data(config: dict) -> List[Fixture]:
    open_cfg = (config.get("gms", {}) or {}).get("open_data", {})
    base = read_env("GMS_OPEN_BASE_URL") or open_cfg.get("base_url")
    if not base:
        return []
    path = open_cfg.get("fixtures_path", "/fixtures")
    p = open_cfg.get("params", {})
    p_from = p.get("from", "fromDate")
    p_to = p.get("to", "toDate")
    p_org = p.get("org", "orgIds")
    p_page = p.get("page", "page")
    p_size = p.get("page_size", "pageSize")

    days_forward = int(config.get("days_forward", 14))
    now = datetime.utcnow()
    # Only upcoming window for Open Data fetch to reduce payload
    date_from = now.date().isoformat()
    date_to = (now + timedelta(days=days_forward)).date().isoformat()

    org_ids: list[str] = config.get("gms", {}).get("org_ids", [])
    org_param = ",".join(org_ids) if org_ids else None

    items: List[Fixture] = []

    debug_pages: list[dict[str, Any]] = []
    with httpx.Client(base_url=base, timeout=20) as client:
        page = 1
        page_size = 200
        while True:
            params: dict[str, Any] = {
                p_from: date_from,
                p_to: date_to,
                p_page: page,
                p_size: page_size,
            }
            if org_param:
                params[p_org] = org_param
            r = client.get(path, params=params)
            r.raise_for_status()
            data = r.json()
            rows = data.get("data") if isinstance(data, dict) and "data" in data else data
            if not isinstance(rows, list) or not rows:
                debug_pages.append({"page": page, "params": params, "rows": 0})
                break
            mapped = [_map_open_data_item(x) for x in rows]
            items.extend([m for m in mapped if m is not None])
            debug_pages.append({"page": page, "params": params, "rows": len(rows)})
            if len(rows) < page_size:
                break
            page += 1
    # Write debug info
    try:
        import pathlib
        d = pathlib.Path("backend/.cache")
        d.mkdir(parents=True, exist_ok=True)
        (d / "gms_open_data_last.json").write_text(json.dumps({"pages": debug_pages, "count": len(items)}, indent=2), encoding="utf-8")
    except Exception:
        pass
    return items


def fetch(config: dict) -> List[Fixture]:
    if not config.get("feature_flags", {}).get("enable_gms", False):
        return []

    # Prefer Open Data if configured
    open_items = _fetch_open_data(config)
    if open_items:
        return open_items

    # Legacy JSONP fall back
    base = read_env("GMS_BASE_URL") or config.get("gms", {}).get("base_url")
    if not base:
        return []

    api_key = read_env("GMS_API_KEY") or config.get("gms", {}).get("api_key")
    org_ids: list[str] = config.get("gms", {}).get("org_ids", [])
    fixtures: List[Fixture] = []
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None

    with httpx.Client(base_url=base) as client:
        for org in org_ids or [None]:
            params = {"orgId": org} if org else None
            resp = _get(client, "/api/fixtures/jsonp", params=params, headers=headers)
            data = _parse_jsonp(resp.text)
            for item in data.get("fixtures", data if isinstance(data, list) else []):
                try:
                    fixtures.append(Fixture(**item, source="gaa_gms"))
                except Exception:
                    continue

    if not fixtures:
        return []
    return fixtures
