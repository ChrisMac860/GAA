from __future__ import annotations

import json
from typing import Any, List

import httpx
from tenacity import retry, wait_exponential, stop_after_attempt

from ..models import Fixture
from ..utils import read_env


@retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
def _get(client: httpx.Client, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> httpx.Response:
    return client.get(url, params=params, headers=headers, timeout=15)


def _fallback_seed() -> List[Fixture]:
    return []


def fetch(config: dict) -> List[Fixture]:
    if not config.get("feature_flags", {}).get("enable_clubzap", False):
        return []

    base = config.get("clubzap", {}).get("base_url", "https://api.clubzap.com")
    jwt = read_env("CLUBZAP_JWT") or config.get("clubzap", {}).get("jwt")
    orgs: list[str] = config.get("clubzap", {}).get("orgs", [])
    if not jwt:
        return []

    headers = {"Authorization": f"Bearer {jwt}"}
    fixtures: List[Fixture] = []
    with httpx.Client(base_url=base) as client:
        for org in orgs:
            try:
                resp = _get(client, f"/orgs/{org}/fixtures")
                data = resp.json()
                for item in data.get("fixtures", data if isinstance(data, list) else []):
                    try:
                        fixtures.append(Fixture(**item, source="clubzap"))
                    except Exception:
                        continue
            except Exception:
                continue
    if not fixtures:
        return []
    return fixtures
