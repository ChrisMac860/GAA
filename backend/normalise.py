from __future__ import annotations

import re
import unicodedata
from typing import Iterable
import re as _re

from .irish_map import IRISH_TO_ENGLISH
from .models import Fixture


_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s-]+")
_WS_RE = re.compile(r"\s+")


def strip_diacritics(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


def norm_text(s: str) -> str:
    s = s.lower()
    s = strip_diacritics(s)
    s = _NON_ALNUM_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def map_irish_tokens(s: str) -> str:
    tokens = norm_text(s).split(" ")
    mapped = [IRISH_TO_ENGLISH.get(tok, tok) for tok in tokens]
    return " ".join(mapped)


def build_search_index(fixtures: Iterable[Fixture]) -> None:
    """Mutates fixtures to include a search_index field combining mapped and original tokens."""
    for f in fixtures:
        parts = [f.home, f.away, f.competition, f.venue or ""]
        orig = " ".join(parts)
        mapped = map_irish_tokens(orig)
        f.search_index = norm_text(orig + " " + mapped)


# Backend equivalent of frontend isPlaceholderTeam to drop placeholder matchups at source
_PLACEHOLDER_SIMPLE = _re.compile(r"(^|\b)(tbd|tba|tbc|bye|unknown|to be (confirmed|decided))($|\b)", _re.I)
_PLACEHOLDER_STAGE = _re.compile(
    r"(quarter\s*final|semi\s*final|final|prelim|preliminary|qualifier|play[- ]?off|round\s*\d+)",
    _re.I,
)
_PLACEHOLDER_GROUP = _re.compile(r"(group\s*[a-z]|group\s*\d+|pool\s*[a-z]|pool\s*\d+)", _re.I)
_PLACEHOLDER_SHORT = _re.compile(r"(^|\b)(qf|sf|rf|r\d{1,2})(\b|$)", _re.I)


def is_placeholder_team(name: str) -> bool:
    if not name:
        return True
    raw = name.strip()
    s = strip_diacritics(raw).lower()

    if _PLACEHOLDER_SIMPLE.search(raw):
        return True

    ph_words = [
        "winner",
        "loser",
        "runner-up",
        "runner up",
        "runners-up",
        "runners up",
        "top team",
        "first place",
        "second place",
        "third place",
        "4th place",
        "1st place",
        "2nd place",
        "3rd place",
    ]
    if any(w in s for w in ph_words):
        return True

    if _PLACEHOLDER_STAGE.search(s):
        return True
    if _PLACEHOLDER_GROUP.search(s):
        return True
    if _PLACEHOLDER_SHORT.search(s):
        return True

    # Ambiguous placeholders like "Team A/Team B" often used pre-decider (but ensure not genuine vs)
    if _re.match(r"^[^vvs]+/.+$", raw, _re.I) and not _re.search(r"\b(v|vs|versus)\b", raw, _re.I):
        return True

    return False
