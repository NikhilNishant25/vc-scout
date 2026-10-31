from __future__ import annotations
import time
from urllib.parse import urlparse
from .. import http
from ..models import RawSignal
from ..resolve import reg_domain
from ..terms import variants


def collect(thesis):
    days = {"idea": 120, "pre-seed": 180, "seed": 365, "series-a": 540}[thesis["inputs"]["stage"]]
    since = int(time.time() - days * 86400)
    out, seen, errors = [], set(), []
    terms = [v for t in (thesis.get("search_terms") or thesis["keywords"]["core"])[:8] for v in variants(t)]
    for kw in list(dict.fromkeys(terms)):
        try:
            r = http.request("GET", "https://hn.algolia.com/api/v1/search",
                             params={"query": kw, "tags": "show_hn", "numericFilters": f"created_at_i>{since}", "hitsPerPage": 30},
                             ttl=6 * 3600)
        except Exception as e:
            print(f"[warn] hn search failed for '{kw}': {e}")
            errors.append(str(e))
            continue
        for h in r.get("hits", []):
            if h["objectID"] in seen:
                continue
            seen.add(h["objectID"])
            url, title = h.get("url") or "", h.get("title") or ""
            name = title.removeprefix("Show HN:").strip()
            for sep in (" – ", " — ", " - ", ": "):
                name = name.split(sep)[0]
            data = {"title": title, "points": h.get("points") or 0, "comments": h.get("num_comments") or 0,
                    "author": h.get("author"), "hn_id": h["objectID"], "matched": kw}
            u = urlparse(url)
            if u.hostname in ("github.com", "www.github.com"):
                parts = [p for p in u.path.split("/") if p]
                if len(parts) >= 2:
                    data["github_repo"] = f"{parts[0]}/{parts[1]}"
            out.append(RawSignal("hn", "show_hn", name[:80] or title[:80], f"https://news.ycombinator.com/item?id={h['objectID']}",
                                 reg_domain(url), h.get("created_at"), data))
    if errors and not out:
        raise RuntimeError(f"all {len(errors)} searches failed; first: {errors[0][:150]}")
    return out
