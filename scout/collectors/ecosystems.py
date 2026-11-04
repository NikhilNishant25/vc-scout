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


def collect(thesis):
    after = (dt.date.today() - dt.timedelta(days=WINDOW[thesis["inputs"]["stage"]])).isoformat()
    out, seen, errors, tried = [], set(), [], 0
    for a in (thesis.get("anchors") or [])[:5]:
        tried += 1
        url = f"{BASE}/{a['registry']}/packages/{a['package']}/dependent_packages"
        params = {"per_page": 100, "created_after": after, "sort": "created_at", "order": "desc"}
        try:
            try:
                items = http.request("GET", url, params=params, ttl=24 * 3600, timeout=90, retries=1)
            except http.HttpError as e:
                if e.code not in (400, 422):
                    raise
                params.pop("sort"); params.pop("order")  # unknown sort value: fall back to the default ordering
                items = http.request("GET", url, params=params, ttl=24 * 3600, timeout=90, retries=1)
        except Exception as e:
            errors.append(f"{a['package']}: {str(e)[:120]}")
            print(f"[warn] ecosystems anchor {a['package']} failed: {e}")
            continue
        for p in items if isinstance(items, list) else []:
            key = (p.get("ecosystem"), p.get("name"))
            if key in seen:
                continue
            seen.add(key)
            out.append(RawSignal("ecosystems", "package", p.get("name", ""), p.get("registry_url") or p.get("homepage") or "",
                                 reg_domain(p.get("homepage")), p.get("first_release_published_at") or p.get("created_at"),
                                 {"description": p.get("description"), "github_repo": _gh_repo(p.get("repository_url")),
                                  "downloads": p.get("downloads") or 0, "dependent_repos": p.get("dependent_repos_count") or 0,
                                  "keywords": p.get("keywords_array"), "anchor": a["package"], "funding_links": p.get("funding_links")}))
    if tried and errors and not out:
        raise RuntimeError(f"all {len(errors)} anchors failed; first: {errors[0]}")
    return out
