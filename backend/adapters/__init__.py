from .gaa_gms import fetch as fetch_gms
from .clubzap import fetch as fetch_clubzap
from .ics_ecal import fetch as fetch_ics
from .scraper_web import fetch as fetch_scraper

__all__ = [
    "fetch_gms",
    "fetch_clubzap",
    "fetch_ics",
    "fetch_scraper",
]
