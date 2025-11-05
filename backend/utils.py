from __future__ import annotations

import os
import pathlib
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Iterable

import orjson

LONDON_TZ = "Europe/London"


def ensure_dir(p: str | pathlib.Path) -> None:
    pathlib.Path(p).mkdir(parents=True, exist_ok=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    # lightweight slugify
    import re
    import unicodedata

    value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"\s+", "-", value).strip("-")
    value = re.sub(r"-+", "-", value)
    return value


def write_json(path: str | pathlib.Path, data) -> None:
    ensure_dir(pathlib.Path(path).parent)
    with open(path, "wb") as f:
        f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))


def read_env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def london_weekend_for(dt: date) -> tuple[date, date]:
    # Saturday..Sunday for the week of dt
    dow = dt.weekday()  # Monday=0
    # We want Saturday (5) and Sunday (6)
    delta_to_sat = (5 - dow) % 7
    sat = dt + timedelta(days=delta_to_sat)
    sun = sat + timedelta(days=1)
    return sat, sun


def in_range(day: date, start: date, end: date) -> bool:
    return start <= day <= end


def to_london_date_time(dt: datetime) -> tuple[str, str]:
    tz = ZoneInfo("Europe/London")
    local = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")
