"""GitHub discovery + enrichment. Failures on a single repo never kill the run."""
import datetime as dt
import os
import requests

API = "https://api.github.com"


def _headers(raw=False):
    h = {"Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json"}
    tok = os.getenv("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _get(path, raw=False, **params):
    r = requests.get(f"{API}{path}", headers=_headers(raw), params=params, timeout=30)
    r.raise_for_status()
    return r.text if raw else r.json()


def discover(cfg):
    since = (dt.date.today() - dt.timedelta(days=cfg["window_days"])).isoformat()
    found = {}
    for topic in cfg["topics"]:
        q = (f"topic:{topic} created:>{since} stars:{cfg['stars_min']}..{cfg['stars_max']} "
             "fork:false archived:false")
        try:
            items = _get("/search/repositories", q=q, sort="stars", order="desc", per_page=30)["items"]
        except requests.RequestException as e:
            print(f"[warn] search failed for {topic}: {e}")
            continue
        for r in items:
            found[r["full_name"]] = r
    return list(found.values())


def enrich(repo):
    full = repo["full_name"]
    now = dt.datetime.now(dt.timezone.utc)
    since30 = (now - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {"repo": repo}

    def safe(fn, default):
        try:
            return fn()
        except requests.RequestException:
            return default

    commits = safe(lambda: _get(f"/repos/{full}/commits", since=since30, per_page=100), [])
    out["commits_30d"] = len(commits)
    out["authors_30d"] = len({c["author"]["login"] for c in commits if c.get("author")})
    releases = safe(lambda: _get(f"/repos/{full}/releases", per_page=3), [])
    out["last_release"] = releases[0]["published_at"] if releases else None
    out["owner"] = safe(lambda: _get(f"/users/{repo['owner']['login']}"), {})
    out["readme"] = safe(lambda: _get(f"/repos/{full}/readme", raw=True), "")
    created = dt.datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
    out["age_days"] = max(1, (now - created).days)
    return out
