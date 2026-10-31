from __future__ import annotations
import datetime as dt, time
from .. import github_signals as gh
from ..models import RawSignal
from ..resolve import reg_domain
from ..terms import variants

# stage -> (window days, star band): earlier stages look at younger, smaller repos (many real early projects have <10 stars)
BANDS = {"idea": (150, (0, 300)), "pre-seed": (270, (1, 1500)), "seed": (365, (5, 5000)), "series-a": (730, (50, 20000))}


def collect(thesis):
    days, (lo, hi) = BANDS[thesis["inputs"]["stage"]]
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    out, seen, errors = [], set(), []
    for term in (thesis.get("search_terms") or thesis["keywords"]["core"])[:8]:
        got = 0
        for v in variants(term):
            if got >= 5:
                break
            q = f'"{v}" in:name,description,readme created:>{since} stars:{lo}..{hi} fork:false archived:false'
            try:
                items = gh.search_repos(q)
            except Exception as e:
                print(f"[warn] github search failed for '{v}': {e}")
                errors.append(str(e))
                continue
            time.sleep(2.1)  # GitHub search allows ~30 requests/minute
            for r in items:
                if r["full_name"] in seen:
                    continue
                seen.add(r["full_name"])
                got += 1
                out.append(RawSignal("github", "repo", r["full_name"], r["html_url"], reg_domain(r.get("homepage")), r["created_at"],
                                     {"full_name": r["full_name"], "stars": r["stargazers_count"], "forks": r["forks_count"],
                                      "description": r.get("description"), "language": r.get("language"),
                                      "matched": v, "repo": r}))
    if errors and not out:
        raise RuntimeError(f"all {len(errors)} searches failed; first: {errors[0][:150]}")
    return out
