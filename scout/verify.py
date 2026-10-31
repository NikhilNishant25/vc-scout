"""Verification: rules decide the tier. Every tier stores the evidence behind it."""
from __future__ import annotations
import datetime as dt, os, re
from . import github_signals, http
from .resolve import norm_name, reg_domain

PARKED = ["domain is for sale", "buy this domain", "this domain may be for sale", "domain for sale", "parked free"]
PRODUCT = re.compile(r"\b(pricing|sign up|get started|book a demo|request a demo|waitlist|free trial|early access|download)\b", re.I)
TEAM = re.compile(r"\b(about us|our team|meet the team|founders?|co-founder|who we are)\b", re.I)
BOARDS = [("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{s}/jobs", lambda j: len(j.get("jobs", []))),
          ("lever", "https://api.lever.co/v0/postings/{s}?mode=json", lambda j: len(j) if isinstance(j, list) else 0),
          ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{s}", lambda j: len(j.get("jobs", [])))]


def _strip(html):
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()


def check_site(domain):
    err = "unreachable"
    for scheme in ("https", "http"):
        try:
            r = http.request("GET", f"{scheme}://{domain}", text=True, ttl=12 * 3600, timeout=15, retries=1)
        except Exception as e:
            err = str(e)[:120]
            continue
        if r["status"] >= 400:
            return {"live": False, "reason": f"HTTP {r['status']}"}
        html = r["text"]
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        title = re.sub(r"\s+", " ", m.group(1)).strip()[:160] if m else ""
        text = _strip(html)[:20000]
        low = (title + " " + text).lower()
        years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)[^0-9]{0,20}((?:19|20)\d\d)", html, flags=re.I)]
        return {"live": True, "url": r["url"], "title": title, "text": text,
                "parked": any(p in low for p in PARKED), "product": bool(PRODUCT.search(text)),
                "team": bool(TEAM.search(text)), "copyright_year": max(years) if years else None}
    return {"live": False, "reason": err}


def check_hiring(domain, name):
    base = domain.split(".")[0] if domain else ""
    slugs = [s for s in dict.fromkeys([base, re.sub(r"[^a-z0-9]", "", name.lower()), re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")]) if len(s) >= 3]
    for s in slugs:
        for board, url, count in BOARDS:
            try:
                n = count(http.request("GET", url.format(s=s), ttl=24 * 3600, retries=0))
            except Exception:
                continue
            if n:
                return {"count": n, "board": board, "slug": s, "url": url.format(s=s)}
    return {}


def check_registry(c, country):
    ch = next((s for s in c.signals if s.source == "companies_house"), None)
    if ch:
        return {"matched": True, "type": "companies_house", "number": ch.data.get("company_number"), "url": ch.url}
    want = norm_name(c.name)
    try:
        if country == "UK" and os.getenv("COMPANIES_HOUSE_KEY"):
            r = http.request("GET", "https://api.company-information.service.gov.uk/search/companies",
                             params={"q": c.name, "items_per_page": 5}, auth=(os.environ["COMPANIES_HOUSE_KEY"], ""), ttl=7 * 86400)
            for it in r.get("items", []):
                if norm_name(it.get("title")) == want and it.get("company_status") == "active":
                    return {"matched": True, "type": "companies_house", "number": it.get("company_number"),
                            "url": f"https://find-and-update.company-information.service.gov.uk/company/{it.get('company_number')}"}
        if country == "US" and os.getenv("SEC_USER_AGENT"):
            r = http.request("GET", "https://efts.sec.gov/LATEST/search-index", params={"q": f'"{c.name}"', "forms": "D"},
                             headers={"User-Agent": os.environ["SEC_USER_AGENT"]}, ttl=7 * 86400)
            for h in r.get("hits", {}).get("hits", []):
                for dn in h.get("_source", {}).get("display_names", []):
                    if norm_name(dn.split("(")[0]) == want:
                        return {"matched": True, "type": "sec_form_d", "url": "https://www.sec.gov/search-filings"}
    except Exception as e:
        return {"matched": False, "error": str(e)[:120]}
    return {"matched": False, "manual_lookup": True}


def check_github(c):
    gs = [s for s in c.signals if s.source == "github" and s.data.get("repo")]
    if not gs:
        return {}
    best = max(gs, key=lambda s: s.data.get("stars", 0))
    e = github_signals.enrich(best.data["repo"])
    e["repo"] = best.name
    e["url"] = best.url
    return e


def check_ecosystem(c):
    gs = [s for s in c.signals if s.source == "github"]
    if not gs:
        return {}
    full = max(gs, key=lambda s: s.data.get("stars", 0)).data["full_name"]
    name = full.split("/")[1].lower()
    for reg in ("npmjs.org", "pypi.org"):
        try:
            r = http.request("GET", f"https://packages.ecosyste.ms/api/v1/registries/{reg}/packages/{name}", ttl=7 * 86400, retries=0)
        except Exception:
            continue
        if full.lower() in (r.get("repository_url") or "").lower():
            return {"registry": reg, "package": name, "dependent_repos": r.get("dependent_repos_count"),
                    "dependent_packages": r.get("dependent_packages_count"), "downloads": r.get("downloads"),
                    "funding_links": r.get("funding_links")}
    return {}


def anti_flags(c, ev, thesis):
    flags = []
    if ev["site"].get("parked"):
        flags.append("parked-domain")
    if ev["github"].get("archived"):
        flags.append("archived-repo")
    text = " ".join([c.name, ev["site"].get("title", "")] + [str(s.data.get("description") or s.data.get("tagline") or "") for s in c.signals]).lower()
    for w in thesis["keywords"]["negative"] + thesis.get("anti_signals", []):
        if re.search(rf"\b{re.escape(w)}\b", text):
            flags.append(f"negative-keyword:{w}")
    return flags


def assess(f):
    """Pure tier logic. f: live, parked, product, team, recent, hiring, registry, families (int), flags (list)."""
    conf = (0.20 * f["product"] + 0.10 * f["team"] + 0.20 * f["hiring"] + 0.25 * f["registry"] + 0.15 * f["recent"]
            + 0.10 * min(1.0, max(0, f["families"] - 1) / 2))
    conf = round(conf, 3)
    if f["flags"] or not f["live"] or f["parked"]:
        return "Unverified", conf
    entity = f["registry"] or (f["hiring"] and f["team"] and f["families"] >= 2)
    if entity and f["product"] and f["recent"] and f["families"] >= 2:
        return "Verified-operating", conf
    if f["product"] and (f["team"] or f["hiring"]) and f["recent"]:
        return "Likely", conf
    return "Unverified", conf


def verify(c, thesis):
    country = thesis["geo"]["country"]
    ev = {"github": check_github(c)}
    if not c.domains:
        d = reg_domain(ev["github"].get("owner_blog"))
        if d:
            c.domains.append(d)
            c.flags.append("domain-from-owner-blog")
    dom = c.domains[0] if c.domains else None
    ev["site"] = check_site(dom) if dom else {"live": False, "reason": "no domain found"}
    ev["hiring"] = check_hiring(dom, c.name) if dom else {}
    ev["registry"] = check_registry(c, country)
    ev["ecosystem"] = check_ecosystem(c)
    now = dt.datetime.now(dt.timezone.utc)

    def within(ts, days):
        try:
            return (now - dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))).days <= days
        except Exception:
            return False
    recent = ((ev["github"].get("commits_30d") or 0) > 0 or bool(ev["hiring"])
              or any(s.source in ("hn", "producthunt") and s.ts and within(s.ts, 180) for s in c.signals)
              or (ev["site"].get("copyright_year") or 0) >= now.year - 1)
    families = {s.source for s in c.signals}
    if ev["hiring"]:
        families.add("careers")
    if ev["registry"].get("matched"):
        families.add("registry")
    flags = anti_flags(c, ev, thesis)
    tier, conf = assess({"live": ev["site"].get("live", False), "parked": ev["site"].get("parked", False),
                         "product": ev["site"].get("product", False), "team": ev["site"].get("team", False),
                         "recent": recent, "hiring": bool(ev["hiring"]), "registry": bool(ev["registry"].get("matched")),
                         "families": len(families), "flags": flags})
    links = [{"label": f"{s.source}: {s.name}", "url": s.url} for s in c.signals]
    if ev["hiring"]:
        links.append({"label": f"jobs ({ev['hiring']['board']})", "url": ev["hiring"]["url"]})
    if ev["registry"].get("url"):
        links.append({"label": "registry", "url": ev["registry"]["url"]})
    if ev["github"].get("errors"):
        c.flags.append("github-data-incomplete")
    ev["links"], ev["families"] = links, sorted(families)
    c.evidence, c.flags, c.tier, c.confidence = ev, c.flags + flags, tier, conf
    return c
