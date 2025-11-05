from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

Status = Literal["scheduled", "FT", "PP"]


class Fixture(BaseModel):
    id: str
    date: str  # YYYY-MM-DD (Europe/London)
    time: str  # HH:mm (24h)
    competition: str
    home: str
    away: str
    venue: Optional[str] = None
    status: Status = "scheduled"
    score: Optional[str] = ""
    source: str  # "gaa_gms" | "clubzap" | "ics" | "scraper"
    updated_at: str  # ISO8601 Z
    # Ephemeral search index (not required in outputs). Left included for potential downstream usage.
    search_index: Optional[str] = Field(default=None)


class Competition(BaseModel):
    name: str
    slug: str
    popularity: int
    match_count: int
    first_kickoff: str  # ISO8601

