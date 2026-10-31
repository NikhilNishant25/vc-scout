from __future__ import annotations
import datetime as dt
from .. import github_signals as gh
from ..models import RawSignal
from ..resolve import reg_domain

# stage -> (window days, star band): earlier stages look at younger, smaller repos
BANDS = {"idea": (120, (3, 300)), "pre-seed": (180, (10, 1500)), "seed": (365, (30, 5000)), "series-a": (730, (200, 20000))}


def collect(thesis):
    days, (lo, hi) = BANDS[thesis["inputs"]["stage"]]
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    out, seen, errors = [], set(), []
    for kw in (thesis.get("search_terms") or thesis["keywords"]["core"])[:6]:
        q = f'"{kw}" in:name,description,readme created:>{since} stars:{lo}..{hi} fork:false archived:false'
        try:
            items = gh.search_repos(q)
        except Exception as e:
            print(f"[warn] github search failed for '{kw}': {e}")
            errors.append(str(e))
            continue
        for r in items:
            if r["full_name"] in seen:
                continue
            seen.add(r["full_name"])
            out.append(RawSignal("github", "repo", r["full_name"], r["html_url"], reg_domain(r.get("homepage")), r["created_at"],
                                 {"full_name": r["full_name"], "stars": r["stargazers_count"], "forks": r["forks_count"],
                                  "description": r.get("description"), "language": r.get("language"),
                                  "matched": kw, "repo": r}))
    if errors and not out:
        raise RuntimeError(f"all {len(errors)} searches failed; first: {errors[0][:150]}")
    return out
