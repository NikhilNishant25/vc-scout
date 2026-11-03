from __future__ import annotations
import datetime as dt, json, math, os, pathlib, re

TIER = {"Verified-operating": 0, "Likely": 1, "Unverified": 2}
SNAP = pathlib.Path(os.getenv("SCOUT_SNAP", "data/snapshots"))


def _clip(x):
    return max(0.0, min(1.0, x))


def _blob(c):
    site = c.evidence.get("site", {})
    parts = [c.name] + [str(s.data.get("description") or s.data.get("tagline") or s.data.get("title") or "") for s in c.signals]
    return " ".join(parts + [site.get("title", ""), site.get("text", "")[:3000], c.evidence.get("github", {}).get("readme_excerpt", "")]).lower()


from .terms import phrase_score  # noqa: E402


def fit(c, thesis):
    blob = _blob(c)
    core = sum(phrase_score(k, blob) for k in thesis["keywords"]["core"])
    adj = sum(phrase_score(k, blob) for k in thesis["keywords"]["adjacent"])
    neg = sum(re.search(rf"\b{re.escape(k)}\b", blob) is not None for k in thesis["keywords"]["negative"])
    return round(_clip(0.8 * min(1, core / 2) + 0.2 * min(1, adj / 2) - 0.25 * min(2, neg)), 3)


def _max(c, source, key):
    return max([s.data.get(key, 0) or 0 for s in c.signals if s.source == source] or [0])


def stealth(c, known):
    if any(d in known for d in c.domains):
        c.flags.append("already-known")
        return 0.0
    exposure = (0.5 * min(1, math.log10(1 + _max(c, "github", "stars")) / 3.5)
                + 0.25 * min(1, _max(c, "hn", "points") / 300) + 0.25 * min(1, _max(c, "producthunt", "votes") / 500))
    return round(1 - _clip(exposure), 3)


def _prev(c):
    try:
        return json.loads((SNAP / f"{c.id}.jsonl").read_text().strip().splitlines()[-1])
    except (OSError, ValueError, IndexError):
        return None


def momentum(c):
    g, h, eco = c.evidence.get("github", {}), c.evidence.get("hiring", {}), c.evidence.get("ecosystem", {})
    stars = _max(c, "github", "stars")
    age = g.get("age_days") or 90
    m = (0.35 * min(1, (g.get("commits_30d") or 0) / 40) + 0.25 * min(1, stars / age / 3)
         + 0.20 * min(1, h.get("count", 0) / 5) + 0.10 * min(1, (eco.get("dependent_repos") or 0) / 20)
         + 0.10 * min(1, _max(c, "hn", "points") / 150))
    p = _prev(c)
    if p and p.get("stars"):
        m += 0.25 * _clip((stars - p["stars"]) / max(5, p["stars"]))
    return round(_clip(m), 3)


def save_snapshot(c):
    SNAP.mkdir(parents=True, exist_ok=True)
    g = c.evidence.get("github", {})
    row = {"ts": dt.date.today().isoformat(), "stars": _max(c, "github", "stars"), "commits_30d": g.get("commits_30d"),
           "jobs": c.evidence.get("hiring", {}).get("count", 0)}
    with open(SNAP / f"{c.id}.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")


def prelim(c, thesis, known):
    return 0.5 * fit(c, thesis) + 0.3 * momentum(c) + 0.2 * stealth(c, known)


def score(c, thesis, known):
    c.flags = [f for f in c.flags if f != "already-known"]
    c.scores = {"fit": fit(c, thesis), "verification": c.confidence, "momentum": momentum(c), "stealth": stealth(c, known)}
    c.rank_score = round(sum(thesis["weights"][k] * c.scores[k] for k in thesis["weights"]), 4)
    return c


def order(companies):
    return sorted(companies, key=lambda c: (TIER.get(c.tier, 3), -c.rank_score))
