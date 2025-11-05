from __future__ import annotations

from typing import List

from ..models import Fixture


def fetch(config: dict) -> List[Fixture]:
    # Keep behind feature flag and return empty by default to avoid scraping costs.
    if not config.get("feature_flags", {}).get("enable_scraper", False):
        return []
    # Placeholder: implement httpx + selectolax if enabled and whitelisted by robots.txt.
    return []

