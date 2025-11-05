from __future__ import annotations

import re
import unicodedata
from typing import Iterable

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

