"""Shared helpers: polite HTTP client for legislation.gov.uk and paths."""
import os
import threading
import time

import requests

BASE = "https://www.legislation.gov.uk"
UA = "LawCodex/1.0 (+https://github.com/LawCodex)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.environ.get("LAWCODEX_RAW", os.path.join(os.path.dirname(ROOT), "_raw", "gb"))

# Primary legislation types fetched (directory = legislation.gov.uk type code).
TYPES = [
    "ukpga",  # UK Public General Acts (incl. pre-1800 Acts of the Parliament of GB/England in some cases)
    "ukla",   # UK Local Acts (only those with XML text)
    "ukppa",  # UK Private and Personal Acts
    "ukcm",   # Church Measures
    "apgb",   # Acts of the Parliament of Great Britain 1707-1800
    "gbla",   # Local Acts of the Parliament of Great Britain
    "aep",    # Acts of the English Parliament (to 1707)
    "aosp",   # Acts of the Old Scottish Parliament (to 1707)
    "aip",    # Acts of the Old Irish Parliament (to 1800)
    "asp",    # Acts of the Scottish Parliament
    "asc",    # Acts of Senedd Cymru
    "anaw",   # Acts of the National Assembly for Wales
    "mwa",    # Measures of the National Assembly for Wales
    "nia",    # Acts of the Northern Ireland Assembly
    "mnia",   # Measures of the Northern Ireland Assembly
    "apni",   # Acts of the Northern Ireland Parliament (1921-1972)
]

# Minimum seconds between the start of two requests (global, across threads).
MIN_INTERVAL = float(os.environ.get("LAWCODEX_MIN_INTERVAL", "0.4"))

_lock = threading.Lock()
_last = [0.0]
_local = threading.local()


def _session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = UA
        _local.s = s
    return s


def _throttle():
    with _lock:
        now = time.monotonic()
        wait = _last[0] + MIN_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def get(url, timeout=300, tries=6):
    """GET with global rate limiting and exponential backoff. Returns Response or None for 404."""
    delay = 5
    for attempt in range(tries):
        _throttle()
        try:
            r = _session().get(url, timeout=timeout)
        except requests.RequestException as e:
            err = str(e)
        else:
            if r.status_code == 200:
                return r
            if r.status_code in (404, 410):
                return None
            err = f"HTTP {r.status_code}"
            if r.status_code in (429, 503):
                ra = r.headers.get("Retry-After")
                if ra and ra.isdigit():
                    delay = max(delay, int(ra))
        if attempt < tries - 1:
            time.sleep(delay)
            delay = min(delay * 2, 300)
    raise RuntimeError(f"failed {url}: {err}")
