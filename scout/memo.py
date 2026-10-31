import json
import os

PROMPT = """You are a skeptical early-stage investor's analyst. Write a one-page thesis memo.
Thesis we screen for: {thesis}

Rules: use ONLY the facts below. Mark anything inferred as "(inferred)". Do not invent funding,
traction, customers or team. Be direct about weaknesses.

Sections (markdown): One-liner | Why now | Builder signal | What would make me wrong |
5 questions for the founder | Verdict (Reach out / Watch / Pass) with one-sentence reason.

FACTS:
{facts}
"""


def facts(e, total, signals, hits):
    r = e["repo"]
    return {
        "repo": r["full_name"], "url": r["html_url"], "description": r.get("description"),
        "homepage": r.get("homepage"), "stars": r["stargazers_count"], "forks": r["forks_count"],
        "age_days": e["age_days"], "commits_30d": e["commits_30d"], "authors_30d": e["authors_30d"],
        "last_release": e["last_release"], "language": r.get("language"),
        "owner": {k: e["owner"].get(k) for k in ("login", "name", "company", "followers", "blog", "bio")},
        "commercial_terms_found": hits, "score": total, "signal_breakdown": signals,
        "readme_excerpt": e["readme"][:3000],
    }


def write_memo(e, total, signals, hits, cfg):
    f = facts(e, total, signals, hits)
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return (f"# {f['repo']}\n\nScore {total}\n\n(No ANTHROPIC_API_KEY set: facts only)\n\n"
                f"```json\n{json.dumps({k: v for k, v in f.items() if k != 'readme_excerpt'}, indent=2)}\n```\n")
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=os.getenv("SCOUT_MODEL", "claude-sonnet-5-5"), max_tokens=1500,
        messages=[{"role": "user", "content": PROMPT.format(thesis=cfg["thesis"], facts=json.dumps(f, indent=2))}],
    )
    body = "".join(b.text for b in msg.content if b.type == "text")
    return f"# {f['repo']}  (score {total})\n{f['url']}\n\n{body}\n"
