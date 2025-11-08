from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Iterable, List, Optional

import httpx
from dateutil import parser as dtparser
from selectolax.parser import HTMLParser
from icalendar import Calendar  # type: ignore
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Fixture
from ..utils import iso_z, slugify, to_london_date_time
from urllib.parse import urlparse


TEAM_SPLIT_RE = re.compile(r"\s+(?:v|vs|versus)\.?\s+", re.IGNORECASE)
SCORE_RE = re.compile(r"(\d+\s*-\s*\d+)\s*[–-]\s*(\d+\s*-\s*\d+)")

EXCLUDE_COMP_TOKENS = [
    # codes for non-football
    "hurl", "hurling", "camogie", "ladies", "lgfa", "women", "girls",
    # common hurling acronyms
    "shc", "ihc", "jhc",
    # underage
    "u7", "u8", "u9", "u10", "u11", "u12", "u13", "u14", "u15", "u16", "u17", "u18", "u19", "u20", "u21",
    "under", "minor", "academy", "schools", "freshers", "hec", "higher education",
]

FOOTBALL_HINTS = [
    "football", "senior", "intermediate", "junior", "division", "league", "championship",
    # football acronyms
    "sfc", "ifc", "jfc",
]


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
                ajax_added = 0

                # Province AJAX endpoint (fixtures-results-ajax) if available
                try:
                    ajax_items = _fetch_province_ajax(
                        client,
                        page_url=url,
                        days_prev=max(int(config.get("results_days_back", 60)), int(config.get("days_back", 14))),
                        days_after=max(int(config.get("scraper_days_forward", 42)), int(config.get("days_forward", 14))),
                    )
                    if ajax_items:
                        fixtures.extend([fx for fx in ajax_items if _is_adult_football(fx.competition)])
                        ajax_added = len(ajax_items)
                        rows_found += ajax_added
                except Exception:
                    pass
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
                prov = _parse_province_fixtures_dom_order(doc, url)
                if prov:
                    fixtures.extend([fx for fx in prov if _is_adult_football(fx.competition)])
                    rows_found += len(prov)

                # Leinster theme (list inside .data_data)
                try:
                    lein = _parse_leinster_list(doc, url)
                    if lein:
                        fixtures.extend([fx for fx in lein if _is_adult_football(fx.competition)])
                        rows_found += len(lein)
                except Exception:
                    pass

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

                # Wider Tribe JSON window (1 year back/forward) if still nothing
                if rows_found == 0 and tribe_added == 0:
                    try:
                        today = datetime.utcnow().date()
                        wide = _fetch_wordpress_tribe(
                            client,
                            f"{urlparse(url).scheme}://{urlparse(url).netloc}",
                            today_start=(today - timedelta(days=365)).isoformat(),
                            today_end=(today + timedelta(days=365)).isoformat(),
                        )
                        fixtures.extend(wide)
                        tribe_added += len(wide)
                    except Exception:
                        pass

                # ICS feed fallback via The Events Calendar subscribe link
                if rows_found == 0 and tribe_added == 0:
                    try:
                        ics_items = _fetch_tribe_ical(client, page_url=url)
                        fixtures.extend(ics_items)
                        tribe_added += len(ics_items)
                    except Exception:
                        pass

                # As a last resort, optional headless render to execute JS
                if rows_found == 0 and tribe_added == 0 and (config.get("headless", {}) or {}).get("enable", False):
                    try:
                        rendered = _render_headless(
                            url,
                            wait_selector=(config.get("headless", {}) or {}).get(
                                "wait_selector", "li.fixture-result, .tribe-events, #fixtures, .data_data"
                            ),
                            timeout_ms=int((config.get("headless", {}) or {}).get("timeout_ms", 15000)),
                        )
                        if rendered:
                            doc2 = HTMLParser(rendered)
                            before = len(fixtures)
                            # Re-run parsers on rendered DOM
                            prov2 = _parse_province_fixtures_dom_order(doc2, url)
                            if prov2:
                                fixtures.extend([fx for fx in prov2 if _is_adult_football(fx.competition)])
                            lein2 = _parse_leinster_list(doc2, url)
                            if lein2:
                                fixtures.extend([fx for fx in lein2 if _is_adult_football(fx.competition)])
                            for headers_row, cols in _find_table_rows(doc2):
                                data = _extract_from_table(headers_row, cols)
                                comp = data.get("competition") or ""
                                if not _is_adult_football(comp):
                                    continue
                                dtp = _parse_datetime(data.get("date", ""), data.get("time", ""))
                                if not dtp:
                                    continue
                                date_iso, time_hm = dtp
                                if time_hm == "00:00":
                                    continue
                                if not (start <= date_iso <= end):
                                    continue
                                status_text = (data.get("status") or "").lower()
                                if "postpon" in status_text:
                                    status = "PP"
                                elif "result" in status_text or "full" in status_text or data.get("score"):
                                    status = "FT"
                                else:
                                    status = "scheduled"
                                home = data.get("home") or ""
                                away = data.get("away") or ""
                                score = data.get("score") or ""
                                if not (home and away and comp):
                                    joined = " ".join(cols)
                                    team_parsed = _parse_row_text(joined)
                                    home = home or team_parsed["home"]
                                    away = away or team_parsed["away"]
                                    score = score or team_parsed["score"]
                                if not (home and away and comp):
                                    continue
                                fixtures.append(
                                    Fixture(
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
                                )
                            added = len(fixtures) - before
                            rows_found += added
                    except Exception:
                        pass

                # Probe /wp-json routes for debugging
                probe_routes = None
                try:
                    probe_routes = _probe_wp_json(client, origin)
                except Exception:
                    probe_routes = None

                debug.append({"url": url, "rows_seen": rows_found, "tribe_added": tribe_added, "ajax_added": ajax_added, "fixtures_total": len(fixtures), "wp_routes_hint": probe_routes})
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


def _parse_leinster_list(doc: HTMLParser, page_url: str) -> List[Fixture]:
    """Parse Leinster fixtures/results list structure under .data_data.

    Expected structure:
      <div class="data_data"><ul>
        <h3 class="fix_res_date">Sat 8th Nov 25</h3>
        <li class="fixture-result"> ...
          <div class="home_team"><span class="details"><a>Home</a></span><span class="score">(1-10)</span></div>
          <div class="vrs">v</div>
          <div class="away_team"><span class="score">(0-12)</span><span class="details"><a>Away</a></span></div>
          <div class="more_info">
            <div class="fix-res-competition">Competition Name ...</div>
            <div class="fix-res-venue"><a>Venue</a> 1:30 PM</div>
          </div>
        </li>
      </ul></div>
    """
    out: List[Fixture] = []
    container = doc.css_first('.data_data')
    if container:
        nodes = container.css('h3.fix_res_date, li.fixture-result')
    else:
        # Fallback: scan entire document (useful for AJAX snippets without wrapper)
        nodes = doc.css('h3.fix_res_date, li.fixture-result')
        if not nodes:
            return out
    if not nodes:
        return out

    current_date_iso: Optional[str] = None
    time_pat = re.compile(r"(\d{1,2}:\d{2})\s*(am|pm)?", re.IGNORECASE)

    for node in nodes:
        classes = node.attributes.get('class', '') if hasattr(node, 'attributes') else ''  # type: ignore
        # Date headers
        if 'fix_res_date' in classes:
            date_text = node.text(strip=True)
            try:
                # e.g. "Sat 8th Nov 25"
                dt = dtparser.parse(date_text, dayfirst=True, fuzzy=True)
                current_date_iso = dt.strftime('%Y-%m-%d')
            except Exception:
                current_date_iso = None
            continue

        # Fixture/result rows
        if 'fixture-result' in classes:
            if not current_date_iso:
                continue
            home_el = node.css_first('.home_team .details a')
            away_el = node.css_first('.away_team .details a')
            home = home_el.text(strip=True) if home_el else ''
            away = away_el.text(strip=True) if away_el else ''

            comp_el = node.css_first('.more_info .fix-res-competition')
            competition = comp_el.text(strip=True) if comp_el else ''

            venue_wrap = node.css_first('.more_info .fix-res-venue')
            venue_el = node.css_first('.more_info .fix-res-venue a')
            venue = venue_el.text(strip=True) if venue_el else None
            # Extract time from the remaining text within the venue block
            time_text = ''
            if venue_wrap:
                txt = venue_wrap.text(separator=' ', strip=True)
                m = time_pat.search(txt)
                if m:
                    raw_time = m.group(0)
                    try:
                        dt = dtparser.parse(f"{current_date_iso} {raw_time}", dayfirst=True)
                        date_iso, time_hm = to_london_date_time(dt)
                    except Exception:
                        date_iso, time_hm = current_date_iso, _norm_time_str(m.group(1))
                else:
                    date_iso, time_hm = current_date_iso, '00:00'
            else:
                date_iso, time_hm = current_date_iso, '00:00'

            # Scores if present (inside parentheses)
            hs = (node.css_first('.home_team .score').text(strip=True) if node.css_first('.home_team .score') else '')
            as_ = (node.css_first('.away_team .score').text(strip=True) if node.css_first('.away_team .score') else '')
            hs_clean = hs.strip('() ')
            as_clean = as_.strip('() ')
            has_numeric = bool(re.search(r"\d", hs_clean + as_clean))
            if has_numeric:
                status = 'FT'
                score = f"{hs_clean} - {as_clean}".strip()
                # If time missing for FT, normalise to 12:00 to keep results
                if time_hm == '00:00' or not time_hm:
                    time_hm = '12:00'
            else:
                status = 'scheduled'
                score = ''
                # Drop placeholder all-day times
                if time_hm == '00:00':
                    # Skip scheduled entries with no time per requirements
                    continue

            if not (home and away and competition):
                continue

            out.append(
                Fixture(
                    id=f"lein-{slugify(page_url)}-{date_iso.replace('-', '')}-{time_hm.replace(':','')}-{slugify(competition or 'football')}-{slugify(home)[:16]}-{slugify(away)[:16]}",
                    date=date_iso,
                    time=time_hm,
                    competition=competition or 'Football',
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


def _fetch_tribe_ical(client: httpx.Client, page_url: str) -> List[Fixture]:
    """Fetch and parse iCalendar feed exposed by The Events Calendar subscribe links.

    Tries common routes:
      - /events/list/?ical=1&tribe_display=all
      - /events/?ical=1&tribe_display=all
      - <page_url>?ical=1&tribe_display=all
    """
    origin = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    candidates = [
        f"{origin}/events/list/?ical=1&tribe_display=all",
        f"{origin}/events/?ical=1&tribe_display=all",
        f"{page_url.rstrip('/')}/?ical=1&tribe_display=all",
    ]
    raw_ics: str | None = None
    for u in candidates:
        try:
            r = client.get(u, timeout=25, follow_redirects=True)
            if r.status_code < 400 and ("BEGIN:VCALENDAR" in r.text or (r.headers.get("Content-Type", "").startswith("text/calendar"))):
                raw_ics = r.text
                break
        except Exception:
            continue
    if not raw_ics:
        return []

    cal = Calendar.from_ical(raw_ics)
    fixtures: List[Fixture] = []
    today = datetime.utcnow().date()

    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        try:
            dt = comp.get("dtstart").dt  # type: ignore[attr-defined]
        except Exception:
            continue
        # dt can be date or datetime
        try:
            if hasattr(dt, "year") and hasattr(dt, "hour"):
                dt_py = dt  # datetime
            else:
                # date only, assume midnight local
                dt_py = datetime(dt.year, dt.month, dt.day)
        except Exception:
            continue
        date_iso, time_hm = to_london_date_time(dt_py)

        # Extract text fields
        summary = str(comp.get("summary") or "")
        location = str(comp.get("location") or "") or None
        cats = comp.get("categories")
        if isinstance(cats, (list, tuple)) and cats:
            competition_hint = str(cats[0])
        else:
            competition_hint = ""

        # Parse teams and potential score from summary/description
        t = _parse_row_text(summary)
        home, away = t.get("home") or "", t.get("away") or ""
        score = t.get("score") or ""

        # Try to infer competition from prefix of summary (before dash/en dash)
        comp_text = competition_hint
        if not comp_text and " v " in summary.lower():
            m = re.split(r"\s[–—-]\s", summary)
            if len(m) >= 2:
                comp_text = m[0].strip()

        # Filter adult football
        if not _is_adult_football(f"{comp_text} {summary}"):
            continue

        # Drop scheduled with 00:00 as per rules
        status = "scheduled"
        if (score or "").strip():
            status = "FT"
            if time_hm == "00:00":
                time_hm = "12:00"
        elif time_hm == "00:00":
            # Skip if no real time
            continue

        if not (home and away):
            continue

        fixtures.append(
            Fixture(
                id=f"ics-{slugify(origin)}-{date_iso.replace('-', '')}-{time_hm.replace(':','')}-{slugify(comp_text or 'football')}-{slugify(home)[:16]}-{slugify(away)[:16]}",
                date=date_iso,
                time=time_hm,
                competition=comp_text or "Football",
                home=home,
                away=away,
                venue=(location or None),
                status=status,  # type: ignore[assignment]
                score=score,
                source="scraper",
                updated_at=iso_z(datetime.utcnow()),
            )
        )

    return fixtures

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
    # Scope to #fixtures first to avoid mixing dates from results tab; fallback to global only if needed.
    current_date_iso: Optional[str] = None
    nodes = []
    try:
        nodes = doc.css('#fixtures .fix_res_date, #fixtures .competition')
    except Exception:
        nodes = []
    if not nodes:
        nodes = doc.css('.fix_res_date, .competition')
    for node in nodes:
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


def _parse_province_fixtures_dom_order(doc: HTMLParser, page_url: str) -> List[Fixture]:
    """Parse province fixtures by walking the DOM in order so each competition
    block inherits the correct date from the nearest preceding fix_res_date.

    This avoids the bug where selecting two separate CSS lists caused all
    competitions to inherit the last date found (e.g., 6 Dec on Ulster).
    """
    out: List[Fixture] = []
    try:
        container = doc.css_first('#fixtures')
    except Exception:
        container = None
    if not container:
        container = doc

    current_date_iso: Optional[str] = None
    # Walk breadth-first through descendants to maintain DOM order
    for node in container.traverse():  # type: ignore[attr-defined]
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
            if time_text == '00:00':
                if status == 'FT':
                    time_text = '12:00'
                else:
                    continue
            score = f"{hst}  {ast}" if (hst or ast) else ''
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


def _fetch_province_ajax(client: httpx.Client, page_url: str, days_prev: int, days_after: int) -> List[Fixture]:
    """Fetch fixtures/results via the shared fixtures-results-ajax endpoint.

    Mapping (based on observed behaviour):
      - Ulster (ulster.gaa.ie) -> owner=2139, base on leinstergaa.ie
      - Connacht (connachtgaa.ie) -> owner=2142, base on connachtgaa.ie
      - Munster (munster.gaa.ie) -> owner=2140, base on leinstergaa.ie
      - Leinster (leinstergaa.ie) -> owner=2141, base on leinstergaa.ie
    """
    host = urlparse(page_url).netloc
    base_by_host = {
        "ulster.gaa.ie": ("https://leinstergaa.ie/fixtures-results/fixtures-results-ajax/", 2139),
        "connachtgaa.ie": ("https://connachtgaa.ie/fixtures-results/fixtures-results-ajax/", 2142),
        "munster.gaa.ie": ("https://leinstergaa.ie/fixtures-results/fixtures-results-ajax/", 2140),
        "leinstergaa.ie": ("https://leinstergaa.ie/fixtures-results/fixtures-results-ajax/", 2141),
    }
    if host not in base_by_host:
        return []
    base, owner = base_by_host[host]

    def get(params: dict) -> str:
        r = client.get(base, params=params, timeout=25)
        if r.status_code >= 400:
            return ""
        return r.text

    items: List[Fixture] = []
    # Results window
    res_html = get({
        "owner": owner,
        "ccAC": 1,
        "resultsOnly": "Y",
        "reverseDateOrder": "Y",
        "noTBC": "Y",
        "includeClubGames": "Y",
        "includeSchoolGames": "N",
        "daysPrevious": int(days_prev),
    })
    if res_html:
        doc = HTMLParser(res_html)
        items.extend(_parse_province_fixtures_dom_order(doc, page_url))

    # Fixtures window
    fix_html = get({
        "owner": owner,
        "ccAC": 1,
        "fixturesOnly": "Y",
        "noTBC": "Y",
        "showByeGames": "N",
        "includeClubGames": "Y",
        "includeSchoolGames": "N",
        "daysAfter": int(days_after),
    })
    if fix_html:
        doc = HTMLParser(fix_html)
        items.extend(_parse_province_fixtures_dom_order(doc, page_url))

    return items

def _render_headless(page_url: str, wait_selector: str, timeout_ms: int) -> Optional[str]:
    """Best-effort headless render using Playwright if installed. Returns HTML or None.

    Controlled by config.headless.enable. Does not install browsers automatically.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        return None
    html: Optional[str] = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(page_url, wait_until="load", timeout=timeout_ms)
            try:
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
            except Exception:
                pass
            html = page.content()
            context.close()
            browser.close()
    except Exception:
        html = None
    return html
