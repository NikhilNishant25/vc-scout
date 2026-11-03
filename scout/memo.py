from __future__ import annotations
import json
from . import llm

PROMPT = """You are a skeptical early-stage investor's analyst. Write a one-page memo.
Thesis: {thesis}

Rules: use ONLY the facts below. End every factual claim with its source as [source: URL] using a URL from "links".
Never cite {} or anything that is not a URL. For data that is missing or empty, write "not found" with no source tag.
Anything inferred must be marked "(inferred)". Do not invent funding, customers, team or traction. Be direct about weaknesses.
Sections (markdown): One-liner | Why now | Evidence of a real operating company | What would make me wrong |
5 questions for the founder | Verdict (Reach out / Watch / Pass) with one-sentence reason.

FACTS:
{facts}
"""


def facts(c):
    ev = c.evidence
    site = ev.get("site", {})
    return {"name": c.name, "domains": c.domains, "tier": c.tier, "confidence": c.confidence, "flags": c.flags,
            "scores": c.scores, "signals": [{"source": s.source, "name": s.name, "url": s.url, "ts": s.ts,
                                             "info": {k: v for k, v in s.data.items() if k != "repo"}} for s in c.signals],
            "site": {k: site.get(k) for k in ("title", "product", "team", "copyright_year")},
            "site_excerpt": site.get("text", "")[:1500],
            "company_signals_claimed_on_own_pages": ev.get("signals"), "hiring": ev.get("hiring"), "registry": ev.get("registry"), "ecosystem": ev.get("ecosystem"),
            "github": {k: v for k, v in ev.get("github", {}).items() if k not in ("owner_blog",)},
            "links": ev.get("links", [])}


def write(c, thesis):
    f = facts(c)
    body = None
    try:
        body = llm.complete(PROMPT.format(thesis=thesis["statement"], facts=json.dumps(f, indent=2, default=str)))
    except Exception as e:
        print(f"[warn] memo failed for {c.name}: {e}")
    head = f"# {c.name}  ({c.tier}, rank {c.rank_score})\n" + "\n".join(f"- {l['label']}: {l['url']}" for l in f["links"]) + "\n\n"
    if body is None:
        slim = {k: v for k, v in f.items() if k != "site_excerpt"}
        return head + "(No LLM memo: no key set or call failed. Facts only.)\n\n```json\n" + json.dumps(slim, indent=2, default=str) + "\n```\n"
    return head + body + "\n"
