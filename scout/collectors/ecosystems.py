"""Reverse-dependency discovery via ecosyste.ms (endpoint and params confirmed from its OpenAPI spec).
Finds recently published packages that depend on the thesis's anchor libraries: real builders, found indirectly."""
from __future__ import annotations
import datetime as dt, re
from .. import http
from ..models import RawSignal
from ..resolve import reg_domain

BASE = "https://packages.ecosyste.ms/api/v1/registries"
WINDOW = {"idea": 120, "pre-seed": 240, "seed": 365, "series-a": 730}


def _gh_repo(url):
    m = re.search(r"github\.com/([^/\s]+)/([^/\s#?.]+)", url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else None


def _ts(p):
    return p.get("first_release_published_at") or p.get("created_at")


def _fetch(url, after):
    """Try progressively simpler queries; returns (items, params used). Server-side date filters may behave unexpectedly,
    so unfiltered variants are filtered client-side by the caller."""
    variants = [{"per_page": 100, "created_after": after, "sort": "created_at", "order": "desc"},
                {"per_page": 100, "created_after": after + "T00:00:00Z", "sort": "created_at", "order": "desc"},
                {"per_page": 100, "sort": "created_at", "order": "desc"},
                {"per_page": 100}]
    for params in variants[:2]:  # server-side date filters, if they work
        try:
            items = http.request("GET", url, params=params, ttl=24 * 3600, timeout=90, retries=1)
        except http.HttpError as e:
            if e.code in (400, 422):
                continue
            raise
        if isinstance(items, list) and items:
            return items, params
    paged, params = [], {"per_page": 100, "sort": "created_at", "order": "desc"}
    for page in range(1, 9):  # fallback: up to 800 dependents, filtered by date on our side
        try:
            items = http.request("GET", url, params={**params, "page": page}, ttl=24 * 3600, timeout=90, retries=1)
        except http.HttpError as e:
            if e.code in (400, 422):
                break
            raise
        if not isinstance(items, list) or not items:
            break
        paged += items
    return paged, params


def collect(thesis):
    after = (dt.date.today() - dt.timedelta(days=WINDOW[thesis["inputs"]["stage"]])).isoformat()
    out, seen, errors, tried = [], set(), [], 0
    for a in (thesis.get("anchors") or [])[:5]:
        tried += 1
        url = f"{BASE}/{a['registry']}/packages/{a['package']}/dependent_packages"
        try:
            items, used = _fetch(url, after)
        except Exception as e:
            errors.append(f"{a['package']}: {str(e)[:120]}")
            print(f"[warn] ecosystems anchor {a['package']} failed: {e}")
            continue
        print(f"[info] ecosystems {a['package']}: {len(items)} items via {sorted((used or {}).keys())}")
        for p in items:
            if (used or {}).get("created_after") is None and not ((_ts(p) or "")[:10] >= after):
                continue  # unfiltered query: keep only packages first published inside the window
            key = (p.get("ecosystem"), p.get("name"))
            if key in seen:
                continue
            seen.add(key)
            out.append(RawSignal("ecosystems", "package", p.get("name", ""), p.get("registry_url") or p.get("homepage") or "",
                                 reg_domain(p.get("homepage")), _ts(p),
                                 {"description": p.get("description"), "github_repo": _gh_repo(p.get("repository_url")),
                                  "downloads": p.get("downloads") or 0, "dependent_repos": p.get("dependent_repos_count") or 0,
                                  "keywords": p.get("keywords_array"), "anchor": a["package"], "funding_links": p.get("funding_links")}))
    if tried and errors and not out:
        raise RuntimeError(f"all {len(errors)} anchors failed; first: {errors[0]}")
    return out
