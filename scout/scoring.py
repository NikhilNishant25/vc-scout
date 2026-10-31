import datetime as dt
import re


def _clip(x):
    return max(0.0, min(1.0, x))


def red_flagged(e, cfg):
    rf = cfg["red_flags"]
    name = e["repo"]["name"].lower()
    if any(re.search(p, name) for p in rf["name_patterns"]):
        return "name pattern (list/tutorial/template)"
    if len(e["readme"]) < rf["min_readme_chars"]:
        return "thin README"
    return None


def score(e, cfg):
    t, w, r = cfg["targets"], cfg["weights"], e["repo"]
    text = (e["readme"] + " " + (r.get("homepage") or "") + " " + (r.get("description") or "")).lower()
    hits = [k for k in cfg["commercial_terms"] if k.lower() in text]
    recent = False
    if e["last_release"]:
        d = dt.datetime.fromisoformat(e["last_release"].replace("Z", "+00:00"))
        recent = (dt.datetime.now(dt.timezone.utc) - d).days <= 30
    stars = max(1, r["stargazers_count"])
    followers = e["owner"].get("followers", 0)
    s = {
        "star_velocity": _clip(stars / e["age_days"] / t["stars_per_day"]),
        "commit_cadence": _clip(e["commits_30d"] / t["commits_30d"]),
        "recent_release": 1.0 if recent else 0.0,
        "commercial_intent": _clip(len(hits) / 3 + (0.3 if r.get("homepage") else 0)),
        "external_pull": _clip(0.5 * _clip(r["forks_count"] / stars / 0.1)
                               + 0.5 * _clip(r["open_issues_count"] / t["open_issues"])),
        "obscurity": 1 - _clip(followers / t["followers_ceiling"]),
        "contributor_breadth": _clip((e["authors_30d"] - 1) / 3) if e["authors_30d"] else 0.0,
    }
    total = sum(s[k] * w[k] for k in w)
    return round(total * 100, 1), s, hits
