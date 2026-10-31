"""Entity resolution. Primary key = registrable domain. Fuzzy-only matches go to a review queue, never auto-merged."""
from __future__ import annotations
import hashlib, re
from difflib import SequenceMatcher
from urllib.parse import urlparse
from .models import Company

BLOCK = {"github.com", "gitlab.com", "twitter.com", "x.com", "producthunt.com", "medium.com", "notion.site",
         "vercel.app", "netlify.app", "herokuapp.com", "github.io", "linkedin.com", "youtube.com", "substack.com",
         "huggingface.co", "pages.dev", "streamlit.app", "replit.app", "wixsite.com", "carrd.co", "webflow.io",
         "ycombinator.com", "news.ycombinator.com", "apps.apple.com", "play.google.com", "chromewebstore.google.com",
         "onrender.com", "fly.dev", "railway.app", "web.app", "firebaseapp.com", "glitch.me", "repl.co", "replit.dev",
         "azurewebsites.net", "cloudfront.net", "amazonaws.com", "appspot.com", "ngrok.io", "ngrok-free.app",
         "trycloudflare.com", "workers.dev", "deno.dev", "surge.sh", "gitbook.io", "bubbleapps.io", "framer.website",
         "framer.app", "lovable.app", "bolt.host", "base44.app", "hf.space", "gradio.live", "supabase.co",
         "google.com", "t.me", "discord.gg", "facebook.com", "instagram.com", "reddit.com", "pypi.org", "npmjs.com"}
MULTI = {"co.uk", "org.uk", "ac.uk", "co.in", "org.in", "com.au", "co.nz", "com.br", "co.jp", "com.sg"}
LEGAL = re.compile(r"\b(inc|ltd|limited|llc|llp|pvt|private|plc|corp|corporation|gmbh|co)\b")
PRI = {"producthunt": 0, "companies_house": 1, "hn": 2, "github": 3}


def reg_domain(u):
    if not u or not isinstance(u, str):
        return None
    u = u.strip()
    if "//" not in u:
        u = "//" + u
    host = (urlparse(u).hostname or "").lower().removeprefix("www.")
    if not host or "." not in host:
        return None
    labels = host.split(".")
    last2, last3 = ".".join(labels[-2:]), ".".join(labels[-3:])
    reg = last3 if last2 in MULTI and len(labels) >= 3 else last2
    return None if (reg in BLOCK or last2 in BLOCK) else reg


def norm_name(s):
    s = LEGAL.sub(" ", (s or "").lower())
    s = re.sub(r"[^a-z0-9]", "", s)
    return s if len(s) >= 3 else ""


def _display(s):
    return s.name.split("/")[-1] if s.source == "github" else s.name


def resolve(signals):
    companies, alias, review = {}, {}, []
    order = sorted(signals, key=lambda s: 0 if (s.domain or s.source == "github") else 1)
    for s in order:
        gh = s.data.get("full_name") if s.source == "github" else s.data.get("github_repo")
        dkey = "d:" + s.domain if s.domain else None
        gkey = "g:" + gh.lower() if gh else None
        nm = norm_name(_display(s))
        nkey = "n:" + nm if nm else None
        cid = next((alias[k] for k in (dkey, gkey) if k and k in alias), None)
        if cid is None and nkey and nkey in alias:
            cand = companies[alias[nkey]]
            gh_names = {(x.data.get("full_name") or x.data.get("github_repo") or "").lower() for x in cand.signals} - {""}
            domain_clash = bool(s.domain and cand.domains and s.domain not in cand.domains)
            repo_clash = bool(gh and gh_names and gh.lower() not in gh_names)
            if not domain_clash and not repo_clash:
                cid = alias[nkey]
        if cid is None and nm and not s.domain:
            for c in companies.values():
                other = norm_name(c.name)
                if other and other != nm:
                    ratio = SequenceMatcher(None, nm, other).ratio()
                    if ratio >= 0.92:
                        review.append({"a": c.name, "b": _display(s), "ratio": round(ratio, 2)})
                        break
        if cid is None:
            cid = hashlib.sha1((dkey or gkey or nkey or s.url).encode()).hexdigest()[:10]
            companies[cid] = Company(id=cid, name=_display(s))
        c = companies[cid]
        c.signals.append(s)
        if s.domain and s.domain not in c.domains:
            c.domains.append(s.domain)
        for k in (dkey, gkey, nkey):
            if k:
                alias.setdefault(k, cid)
    for c in companies.values():
        c.name = _display(min(c.signals, key=lambda s: PRI.get(s.source, 9)))
    return list(companies.values()), review
