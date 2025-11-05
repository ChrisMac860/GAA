from __future__ import annotations

from datetime import datetime
from typing import List

import httpx
from tenacity import retry, wait_exponential, stop_after_attempt
from icalendar import Calendar
from zoneinfo import ZoneInfo

from ..models import Fixture
from ..utils import iso_z


def _parse_event_summary(summary: str) -> tuple[str, str, str]:
    # Heuristic: "Home vs Away - Competition" or "Home v Away (Competition)"
    text = summary.replace(" v ", " vs ")
    comp = ""
    if " - " in text:
        text, comp = text.split(" - ", 1)
    elif " (" in text and text.endswith(")"):
        idx = text.rfind(" (")
        comp = text[idx + 2 : -1]
        text = text[:idx]
    if " vs " in text:
        home, away = [t.strip() for t in text.split(" vs ", 1)]
    else:
        home, away = text, ""
    return home, away, comp


def _fallback_seed() -> List[Fixture]:
    return []


@retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
def _get_ics(url: str) -> bytes:
    headers = {"User-Agent": "gaa-pipeline/0.1 (+https://example.local)"}
    with httpx.Client(headers=headers, timeout=20) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.content


def fetch(config: dict) -> List[Fixture]:
    if not config.get("feature_flags", {}).get("enable_ics", False):
        return []
    urls: list[str] = config.get("ics", {}).get("urls", [])
    if not urls:
        return []

    tz = ZoneInfo("Europe/London")
    out: List[Fixture] = []
    for url in urls:
        try:
            raw = _get_ics(url)
            cal = Calendar.from_ical(raw)
            for component in cal.walk():
                if component.name != "VEVENT":
                    continue
                dtstart = component.get("dtstart").dt  # type: ignore[assignment]
                when: datetime
                if isinstance(dtstart, datetime):
                    when = dtstart.astimezone(tz) if dtstart.tzinfo else dtstart.replace(tzinfo=tz)
                else:
                    when = datetime.combine(dtstart, datetime.min.time(), tz)
                date_str = when.strftime("%Y-%m-%d")
                time_str = when.strftime("%H:%M")
                summary = str(component.get("summary", ""))
                home, away, comp = _parse_event_summary(summary)
                out.append(
                    Fixture(
                        id=f"ics-{when.isoformat()}",
                        date=date_str,
                        time=time_str,
                        competition=comp or "Fixture",
                        home=home,
                        away=away,
                        venue=str(component.get("location", "")) or None,
                        status="scheduled",
                        score="",
                        source="ics",
                        updated_at=iso_z(datetime.utcnow()),
                    )
                )
        except Exception:
            continue

    return out or _fallback_seed()
