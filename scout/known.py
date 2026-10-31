"""'Already known' domain list, used to measure stealth. Best effort: a missing list means stealth is unscored by it."""
from __future__ import annotations
import json, os, pathlib
from . import http
from .resolve import reg_domain

PATH = pathlib.Path(os.getenv("SCOUT_KNOWN", "data/known_domains.json"))


def refresh():
    data = http.request("GET", "https://yc-oss.github.io/api/companies/all.json", ttl=0, timeout=60)
    doms = {reg_domain(x.get("website")) for x in data if isinstance(x, dict)} - {None}
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(sorted(doms)))
    return len(doms)


def load():
    try:
        return set(json.loads(PATH.read_text()))
    except (OSError, ValueError):
        return set()
