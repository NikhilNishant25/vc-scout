"""GitHub API helpers (cached). Search is used for discovery, enrich() for verification evidence."""
from __future__ import annotations
import datetime as dt, os
from . import http

API = "https://api.github.com"


def _headers(raw=False):
    h = {"Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json"}
    tok = os.getenv("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def get(path, **params):
    return http.request("GET", API + path, params=params or None, headers=_headers(), ttl=6 * 3600)


def search_repos(q, per_page=30):
    return get("/search/repositories", q=q, sort="stars", order="desc", per_page=per_page).get("items", [])


def _safe(fn, default, errs=None, label=""):
    try:
        return fn()
    except (http.HttpError, RuntimeError, KeyError, ValueError) as e:
        if errs is not None:
            errs.append(f"{label}: {str(e)[:80]}")
        return default


def enrich(repo):
    full = repo["full_name"]
    now = dt.datetime.now(dt.timezone.utc)
    since30 = (now - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    errs = []
    commits = _safe(lambda: get(f"/repos/{full}/commits", since=since30, per_page=100), None, errs, "commits")
    releases = _safe(lambda: get(f"/repos/{full}/releases", per_page=3), None, errs, "releases")
    owner = _safe(lambda: get(f"/users/{repo['owner']['login']}"), {}, errs, "owner")
    rd = _safe(lambda: http.request("GET", f"{API}/repos/{full}/readme", headers=_headers(True), text=True, ttl=24 * 3600), {}, errs, "readme")
    created = dt.datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
    return {
        "commits_30d": len(commits) if isinstance(commits, list) else None,  # None = unknown (API error), not zero
        "authors_30d": len({c["author"]["login"] for c in commits if isinstance(c, dict) and c.get("author")}) if isinstance(commits, list) else None,
        "errors": errs,
        "last_release": releases[0]["published_at"] if isinstance(releases, list) and releases else None,
        "owner_followers": owner.get("followers", 0), "owner_location": owner.get("location"),
        "owner_blog": owner.get("blog"), "owner_company": owner.get("company"),
        "readme_len": len(rd.get("text", "")) if rd.get("status") == 200 else 0,
        "archived": bool(repo.get("archived")), "stars": repo.get("stargazers_count", 0),
        "age_days": max(1, (now - created).days),
    }
