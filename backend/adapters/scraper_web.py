from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Iterable, List, Optional

import httpx
from dateutil import parser as dtparser
from selectolax.parser import HTMLParser
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Fixture
from ..utils import iso_z, slugify, to_london_date_time
from urllib.parse import urlparse


TEAM_SPLIT_RE = re.compile(r"\s+(?:v|vs|versus)\.?\s+", re.IGNORECASE)
SCORE_RE = re.compile(r"(\d+\s*-\s*\d+)\s*[–-]\s*(\d+\s*-\s*\d+)")

EXCLUDE_COMP_TOKENS = [
    # codes for non-football
    "hurl", "camogie", "ladies", "lgfa", "women", "girls",
    # underage
    "u7", "u8", "u9", "u10", "u11", "u12", "u13", "u14", "u15", "u16", "u17", "u18", "u19", "u20", "u21",
    "under", "minor", "academy", "schools", "freshers", "hec", "higher education",
]

FOOTBALL_HINTS = ["football", "senior", "intermediate", "junior", "division", "league", "championship"]


def _is_adult_football(competition_text: str) -> bool:
    t = competition_text.lower()
    if any(tok in t for tok in EXCLUDE_COMP_TOKENS):
        return False
    # Prefer explicit football hints if present
    if "football" in t:
        return True
    # If not explicitly football but contains adult competition words, accept heuristically
    if any(tok in t for tok in FOOTBALL_HINTS) and "hurl" not in t and "camogie" not in t:
        return True
    return False


def _text(el) -> str:
    return el.text(strip=True) if hasattr(el, "text") else str(el)


def _parse_row_text(txt: str) -> dict[str, Any]:
    # Heuristic parsing when we can't map columns
    # Try find score
    score = ""
    m = SCORE_RE.search(txt)
    if m:
        score = f"{m.group(1).replace(' ', '')} – {m.group(2).replace(' ', '')}"
    # Teams
    home = away = ""
    parts = TEAM_SPLIT_RE.split(txt)
    if len(parts) >= 2:
        home = parts[0].strip("-–, ")
        away = parts[1].split("(")[0].split("[")[0].strip()
    return {"home": home, "away": away, "score": score}


def _norm_time_str(s: str) -> str:
    s = (s or '').strip()
    m = re.search(r"(\d{1,2})[:\.](\d{2})", s)
    if m:
        h = int(m.group(1))
        mnt = int(m.group(2))
        if h < 24 and mnt < 60:
            return f"{h:02d}:{mnt:02d}"
    # fallback
    return "00:00"


def _find_table_rows(doc: HTMLParser) -> Iterable[list[str]]:
    for table in doc.css("table"):
        headers = [th.text(strip=True).lower() for th in table.css("thead tr th")] or [th.text(strip=True).lower() for th in table.css("tr th")]
        for tr in table.css("tbody tr") or table.css("tr"):
            tds = [td.text(strip=True) for td in tr.css("td")]
            if tds and any(tds):
                yield headers or [], tds


def _extract_from_table(headers: list[str], cols: list[str]) -> dict[str, Any]:
    # Map common columns
    hmap = {h: i for i, h in enumerate(headers)}
    get = lambda *names: next((cols[hmap[n]] for n in names if n in hmap and hmap[n] < len(cols)), "")
    date = get("date", "match date")
    time = get("time", "throw-in", "throw in", "ko", "kick-off", "kick off")
    fixture = get("fixture", "match", "teams")
    competition = get("competition", "comp", "competition name")
    venue = get("venue", "ground")
    status = get("status", "result")
    score = get("score", "result")
    home = away = ""
    if fixture:
        team_parsed = _parse_row_text(fixture)
        home = team_parsed["home"]
        away = team_parsed["away"]
        if not score:
            score = team_parsed["score"]
    return {
        "date": date,
        "time": time,
        "home": home,
        "away": away,
        "competition": competition,
        "venue": venue,
        "status": status,
        "score": score,
    }


def _parse_datetime(date_str: str, time_str: str) -> Optional[tuple[str, str]]:
    try:
        if date_str and time_str:
            dt = dtparser.parse(f"{date_str} {time_str}", dayfirst=True, default=datetime.now())
        elif date_str:
            dt = dtparser.parse(date_str, dayfirst=True, default=datetime.now())
        else:
            return None
        return to_london_date_time(dt)
    except Exception:
        return None


@retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
def _get(client: httpx.Client, url: str) -> httpx.Response:
    return client.get(url, timeout=25)


def fetch(config: dict) -> List[Fixture]:
    if not config.get("feature_flags", {}).get("enable_scraper", False):
        return []

    urls: list[str] = (config.get("scraper", {}) or {}).get("urls", [])
    if not urls:
        return []

    today = datetime.utcnow().date()
    start = (today - timedelta(days=int(config.get("days_back", 14)))).isoformat()
    end = (today + timedelta(days=int(config.get("days_forward", 14)))).isoformat()

    fixtures: List[Fixture] = []
    debug: list[dict[str, Any]] = []

    headers = {"User-Agent": "gaa-scraper/0.1 (+https://example.local)"}
    with httpx.Client(headers=headers) as client:
        for url in urls:
            try:
                resp = _get(client, url)
                html = resp.text
                # Save snapshot for debugging
                try:
                    import pathlib
                    host = urlparse(url).netloc.replace(':','_')
                    (pathlib.Path('backend/.cache')/f'snapshot_{host}.html').write_text(html[:200000], encoding='utf-8')
                except Exception:
                    pass
                doc = HTMLParser(html)
                rows_found = 0
                # Structured data (JSON-LD) first
                for script in doc.css('script[type="application/ld+json"]'):
                    try:
                        data = script.text()
                        blocks = json.loads(data)
                        if isinstance(blocks, dict):
                            blocks = [blocks]
                        for blk in blocks or []:
                            if not isinstance(blk, dict):
                                continue
                            if blk.get('@type') not in ('Event','SportsEvent'):
                                continue
                            title = blk.get('name') or ''
                            comp = blk.get('eventType') or blk.get('superEvent',{}).get('name') or ''
                            if not _is_adult_football(f"{comp} {title}"):
                                continue
                            start_dt = blk.get('startDate')
                            if not start_dt:
                                continue
                            dt = dtparser.parse(start_dt)
                            date_iso, time_hm = to_london_date_time(dt)
                            teams = _parse_row_text(title)
                            home, away = teams['home'], teams['away']
                            if not (home and away):
                                continue
                            venue = None
                            loc = blk.get('location')
                            if isinstance(loc, dict):
                                venue = loc.get('name') or None
                            fixtures.append(
                                Fixture(
                                    id=f"ld-{slugify(url)}-{date_iso.replace('-', '')}-{time_hm.replace(':','')}-{slugify(home)[:16]}-{slugify(away)[:16]}",
                                    date=date_iso,
                                    time=time_hm,
                                    competition=comp or 'Football',
                                    home=home,
                                    away=away,
                                    venue=venue,
                                    status='scheduled',  # type: ignore[assignment]
                                    score='',
                                    source='scraper',
                                    updated_at=iso_z(datetime.utcnow()),
                                )
                            )
                            rows_found += 1
                    except Exception:
                        continue
                # Province theme fixtures (Ulster style)
                prov = _parse_province_fixtures(doc, url)
                if prov:
                    fixtures.extend([fx for fx in prov if _is_adult_football(fx.competition)])
                    rows_found += len(prov)

                # Province theme results (explicitly within #results)
                prov_results = _parse_province_results(doc, url)
                if prov_results:
                    fixtures.extend([fx for fx in prov_results if _is_adult_football(fx.competition)])
                    rows_found += len(prov_results)

                # Prefer tables first
                for headers_row, cols in _find_table_rows(doc):
                    rows_found += 1
                    data = _extract_from_table(headers_row, cols)
                    comp = data.get("competition") or ""
                    if not _is_adult_football(comp):
                        continue
                    dt = _parse_datetime(data.get("date", ""), data.get("time", ""))
                    if not dt:
                        continue
                    date_iso, time_hm = dt
                    # Ignore placeholder/all-day rows with 00:00
                    if time_hm == "00:00":
                        continue
                    if not (start <= date_iso <= end):
                        continue
                    # Determine status from status text or score presence
                    status_text = (data.get("status") or "").lower()
                    if "postpon" in status_text:
                        status = "PP"
                    elif "result" in status_text or "full" in status_text or data.get("score"):
                        status = "FT"
                    else:
                        status = "scheduled"

                    home = data.get("home") or ""
                    away = data.get("away") or ""
                    if not home or not away:
                        # Try to parse from any column text joined
                        joined = " ".join(cols)
                        team_parsed = _parse_row_text(joined)
                        home = home or team_parsed["home"]
                        away = away or team_parsed["away"]
                        score = data.get("score") or team_parsed["score"]
                    else:
                        score = data.get("score") or ""

                    if not (home and away and comp):
                        continue

                    fx = Fixture(
                        id=f"scrape-{slugify(url)}-{date_iso.replace('-', '')}-{time_hm.replace(':','')}-{slugify(home)[:16]}-{slugify(away)[:16]}",
                        date=date_iso,
                        time=time_hm,
                        competition=comp,
                        home=home,
                        away=away,
                        venue=(data.get("venue") or None),
                        status=status,  # type: ignore[assignment]
                        score=score or "",
                        source="scraper",
                        updated_at=iso_z(datetime.utcnow()),
                    )
                    fixtures.append(fx)

                # If no table rows, try WordPress Tribe Events REST if available
                tribe_added = 0
                if rows_found == 0:
                    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                    try:
                        tribe = _fetch_wordpress_tribe(
                            client,
                            origin,
                            today_start=(today - timedelta(days=int(config.get("days_back", 14)))).isoformat(),
                            today_end=(today + timedelta(days=int(config.get("days_forward", 14)))).isoformat(),
                        )
                        fixtures.extend(tribe)
                        tribe_added += len(tribe)
                    except Exception:
                        pass

                # Try Tribe views HTML endpoint with full page URL
                if rows_found == 0 and tribe_added == 0:
                    try:
                        tribe2 = _fetch_tribe_views_html(client, page_url=url, days_back=int(config.get("days_back", 14)), days_forward=int(config.get("days_forward", 14)))
                        fixtures.extend(tribe2)
                        tribe_added += len(tribe2)
                    except Exception:
                        pass

                # Probe /wp-json routes for debugging
                probe_routes = None
                try:
                    probe_routes = _probe_wp_json(client, origin)
                except Exception:
                    probe_routes = None

                debug.append({"url": url, "rows_seen": rows_found, "tribe_added": tribe_added, "fixtures_total": len(fixtures), "wp_routes_hint": probe_routes})
            except Exception as e:
                debug.append({"url": url, "error": str(e)})

    # De-duplicate scraper items on (date, time, home, away, competition)
    uniq: list[Fixture] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for fx in fixtures:
        key = (fx.date, fx.time or "", slugify(fx.home), slugify(fx.away), slugify(fx.competition))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(fx)

    # Write debug log
    try:
        import pathlib
        p = pathlib.Path("backend/.cache/scraper_debug.json")
        p.write_text(json.dumps({"pages": debug, "counts": {"raw": len(fixtures), "deduped": len(uniq)}}, indent=2), encoding="utf-8")
    except Exception:
        pass

    return uniq


def _fetch_wordpress_tribe(client: httpx.Client, origin: str, today_start: str, today_end: str) -> List[Fixture]:
    """Fetch events from The Events Calendar (Tribe) REST API if present."""
    fixtures: List[Fixture] = []
    page = 1
    per_page = 100
    while True:
        url = f"{origin}/wp-json/tribe/events/v1/events"
        r = client.get(url, params={"start_date": today_start, "end_date": today_end, "per_page": per_page, "page": page}, timeout=25)
        if r.status_code >= 400:
            break
        data = r.json()
        events = data.get("events") if isinstance(data, dict) else None
        if not events:
            break
        for ev in events:
            title = (ev.get("title") or "").strip()
            # Category or taxonomy name
            comp = ""
            cats = ev.get("categories") or []
            if cats and isinstance(cats, list):
                comp = cats[0].get("name") or comp
            comp = comp or (ev.get("event_category") or "")
            if not _is_adult_football(f"{comp} {title}"):
                continue
            start_date = ev.get("start_date") or ev.get("start_date_details", {}).get("date")
            if not start_date:
                continue
            try:
                dt = dtparser.parse(start_date)
            except Exception:
                continue
            date_iso, time_hm = to_london_date_time(dt)
            if time_hm == '00:00':
                continue
            # Teams from title
            teams = _parse_row_text(title)
            home = teams["home"]
            away = teams["away"]
            if not (home and away):
                continue
            venue = (ev.get("venue") or {}).get("venue") or (ev.get("venue") or {}).get("address") or None
            status = "scheduled"
            score = ""
            fixtures.append(
                Fixture(
                    id=f"tribe-{slugify(origin)}-{date_iso.replace('-', '')}-{time_hm.replace(':','')}-{slugify(comp or 'football')}-{slugify(home)[:16]}-{slugify(away)[:16]}",
                    date=date_iso,
                    time=time_hm,
                    competition=comp or "Football",
                    home=home,
                    away=away,
                    venue=venue,
                    status=status,  # type: ignore[assignment]
                    score=score,
                    source="scraper",
                    updated_at=iso_z(datetime.utcnow()),
                )
            )
        if len(events) < per_page:
            break
        page += 1
    return fixtures


def _probe_wp_json(client: httpx.Client, origin: str) -> list[str] | None:
    r = client.get(f"{origin}/wp-json", timeout=20)
    if r.status_code >= 400:
        return None
    data = r.json()
    routes = data.get("routes", {}) if isinstance(data, dict) else {}
    if not isinstance(routes, dict):
        return None
    names = list(routes.keys())
    hints = [name for name in names if any(k in name for k in ("tribe", "fixtures", "fixture", "events"))]
    return hints[:20]


def _parse_tribe_document(doc: HTMLParser, page_url: str) -> List[Fixture]:
    out: List[Fixture] = []
    # Look for list view articles
    for ev in doc.css('article.tribe-events-calendar-list__event, div.tribe-common-g-row, div.tribe-events-calendar-list__event-row'):
        # Title
        title_el = ev.css_first('a.tribe-events-calendar-list__event-title-link, h3 a, h3')
        title = title_el.text(strip=True) if title_el else ''
        # Datetime
        time_el = ev.css_first('time[datetime]')
        dt_txt = time_el.attributes.get('datetime') if time_el else None  # type: ignore
        if not dt_txt:
            continue
        try:
            dt = dtparser.parse(dt_txt)
        except Exception:
            continue
            date_iso, time_hm = to_london_date_time(dt)
            if time_hm == '00:00':
                continue
        # Venue
        venue_el = ev.css_first('.tribe-events-calendar-list__event-venue, .tribe-events-venue-details, .tribe-venue')
        venue = venue_el.text(strip=True) if venue_el else None
        # Teams from title
        teams = _parse_row_text(title)
        home, away = teams['home'], teams['away']
        comp = ''
        comp_el = ev.css_first('.tribe-events-calendar-list__event-category, .tribe-events-calendar-list__event-cost, .tribe-events-c-small-cta__price')
        comp = comp_el.text(strip=True) if comp_el else ''
        # filter football
        if not _is_adult_football(f"{comp} {title}"):
            continue
        if not (home and away):
            continue
        out.append(
            Fixture(
                id=f"tribehtml-{slugify(page_url)}-{date_iso.replace('-', '')}-{time_hm.replace(':','')}-{slugify(comp or 'football')}-{slugify(home)[:16]}-{slugify(away)[:16]}",
                date=date_iso,
                time=time_hm,
                competition=comp or 'Football',
                home=home,
                away=away,
                venue=venue,
                status='scheduled',  # type: ignore[assignment]
                score='',
                source='scraper',
                updated_at=iso_z(datetime.utcnow()),
            )
        )
    return out


def _fetch_tribe_views_html(client: httpx.Client, page_url: str, days_back: int, days_forward: int) -> List[Fixture]:
    origin = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    endpoint = f"{origin}/wp-json/tribe/views/v2/html"
    start = (datetime.utcnow().date() - timedelta(days=days_back)).isoformat()
    end = (datetime.utcnow().date() + timedelta(days=days_forward)).isoformat()
    params = {
        'view': 'list',
        'url': page_url,
        'start_date': start,
        'end_date': end,
    }
    r = client.get(endpoint, params=params, timeout=25)
    r.raise_for_status()
    # Response is JSON with 'html' or raw HTML depending on version; handle both
    content = r.text
    try:
        data = r.json()
        html = data.get('html') or ''
    except Exception:
        html = content
    if not html:
        return []
    doc = HTMLParser(html)
    return _parse_tribe_document(doc, page_url)


def _parse_province_fixtures(doc: HTMLParser, page_url: str) -> List[Fixture]:
    out: List[Fixture] = []
    # Recognize structure: h3.fix_res_date then multiple div.competition blocks
    current_date_iso: Optional[str] = None
    for node in doc.css('#fixtures .fix_res_date, #fixtures .competition, .fix_res_date, .competition'):
        classes = node.attributes.get('class', '') if hasattr(node, 'attributes') else ''  # type: ignore
        if 'fix_res_date' in classes:
            # date like 'Saturday 8th Nov 2025'
            date_text = node.text(strip=True)
            try:
                dt = dtparser.parse(date_text, dayfirst=True, fuzzy=True)
                current_date_iso = dt.strftime('%Y-%m-%d')
            except Exception:
                current_date_iso = None
            continue
        if 'competition' in classes:
            if not current_date_iso:
                # try fallback by scanning any date tag above
                pass
            comp_name_el = node.css_first('.competition-name')
            comp_name = comp_name_el.text(strip=True) if comp_name_el else ''
            home_el = node.css_first('.home_team a')
            away_el = node.css_first('.away_team a')
            time_el = node.css_first('.time')
            venue_el = node.css_first('.more_info a')
            home_score_el = node.css_first('.home_score')
            away_score_el = node.css_first('.away_score')
            home = home_el.text(strip=True) if home_el else ''
            away = away_el.text(strip=True) if away_el else ''
            time_text = _norm_time_str(time_el.text(strip=True) if time_el else '')
            venue = venue_el.text(strip=True) if venue_el else None
            hst = (home_score_el.text(strip=True) if home_score_el else '')
            ast = (away_score_el.text(strip=True) if away_score_el else '')
            if not (current_date_iso and home and away and time_text is not None):
                continue
            status = 'FT' if (hst or ast) else 'scheduled'
            # If time is 00:00: drop scheduled but keep FT (set fallback 12:00)
            if time_text == '00:00':
                if status == 'FT':
                    time_text = '12:00'
                else:
                    continue
            score = f"{hst} – {ast}" if (hst or ast) else ''
            # Build fixture
            out.append(
                Fixture(
                    id=f"prov-{slugify(page_url)}-{current_date_iso.replace('-', '')}-{time_text.replace(':','')}-{slugify(comp_name or 'football')}-{slugify(home)[:16]}-{slugify(away)[:16]}",
                    date=current_date_iso,
                    time=time_text,
                    competition=comp_name or 'Football',
                    home=home,
                    away=away,
                    venue=venue,
                    status=status,  # type: ignore[assignment]
                    score=score,
                    source='scraper',
                    updated_at=iso_z(datetime.utcnow()),
                )
            )
    return out


def _parse_province_results(doc: HTMLParser, page_url: str) -> List[Fixture]:
    out: List[Fixture] = []
    results = doc.css_first('#results')
    if not results:
        return out
    current_date_iso: Optional[str] = None
    for node in results.css('.fix_res_date, .competition'):
        classes = node.attributes.get('class', '') if hasattr(node, 'attributes') else ''  # type: ignore
        if 'fix_res_date' in classes:
            date_text = node.text(strip=True)
            try:
                dt = dtparser.parse(date_text, dayfirst=True, fuzzy=True)
                current_date_iso = dt.strftime('%Y-%m-%d')
            except Exception:
                current_date_iso = None
            continue
        if 'competition' in classes:
            if not current_date_iso:
                continue
            comp_name_el = node.css_first('.competition-name')
            comp_name = comp_name_el.text(strip=True) if comp_name_el else ''
            home = (node.css_first('.home_team a').text(strip=True) if node.css_first('.home_team a') else '')
            away = (node.css_first('.away_team a').text(strip=True) if node.css_first('.away_team a') else '')
            time_text = _norm_time_str(node.css_first('.time').text(strip=True) if node.css_first('.time') else '')
            hst = (node.css_first('.home_score').text(strip=True) if node.css_first('.home_score') else '')
            ast = (node.css_first('.away_score').text(strip=True) if node.css_first('.away_score') else '')
            venue = (node.css_first('.more_info a').text(strip=True) if node.css_first('.more_info a') else None)
            # Only keep if FT (has a score) and essential fields present
            if not (home and away and (hst or ast)):
                continue
            if time_text == '00:00' or not time_text:
                time_text = '12:00'
            out.append(
                Fixture(
                    id=f"provres-{slugify(page_url)}-{current_date_iso.replace('-', '')}-{time_text.replace(':','')}-{slugify(comp_name or 'football')}-{slugify(home)[:16]}-{slugify(away)[:16]}",
                    date=current_date_iso,
                    time=time_text,
                    competition=comp_name or 'Football',
                    home=home,
                    away=away,
                    venue=venue,
                    status='FT',  # type: ignore[assignment]
                    score=f"{hst} – {ast}",
                    source='scraper',
                    updated_at=iso_z(datetime.utcnow()),
                )
            )
    return out
