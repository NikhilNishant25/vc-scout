"""Industry + stage + location -> keywords + <=3 MCQs -> Thesis. Options must change the search or they are dropped."""
from __future__ import annotations
import datetime as dt, json, pathlib, re, sys
from . import geo, llm

STAGES = ["idea", "pre-seed", "seed", "series-a"]
BASE_WEIGHTS = {"fit": 0.35, "verification": 0.30, "momentum": 0.20, "stealth": 0.15}
DEFAULT_NEG = ["tutorial", "course", "awesome", "template", "boilerplate", "homework", "portfolio", "demo app"]

PROMPT = """You design a sourcing thesis for an early-stage investor.
Industry: {industry}
Stage: {stage}
Location: {location}

Return ONLY JSON with this shape:
{{"keywords": {{"core": [8-12 specific search phrases a real startup in this space would use],
 "adjacent": [6-10 related phrases], "negative": [6-10 words that signal NOT a real startup, e.g. tutorial, course]}},
 "questions": [up to 3 of {{"id": "q1", "text": "...", "options": [{{"label": "...", "adds_keywords": [], "anti_signals": [],
   "must_have": "", "weight_shift": {{"fit": 0, "verification": 0, "momentum": 0, "stealth": 0}}}}]}}]}}

Rules:
- Questions must be specific to THIS industry and stage, not generic investor questions.
- 2 to 4 options per question. Every option MUST change the search: non-empty adds_keywords, anti_signals or must_have, or a nonzero weight_shift (between -0.15 and 0.15).
"""


def _dedupe(xs):
    seen, out = set(), []
    for x in xs:
        x = str(x).strip().lower()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def fallback_design(industry, stage):
    words = [w for w in re.split(r"[^a-z0-9]+", industry.lower()) if len(w) > 2]
    q1 = {"id": "q1", "text": f"What kind of edge should an early {industry} company have?", "options": [
        {"label": "Technical or IP moat", "adds_keywords": ["open source", "benchmark", "patent"], "must_have": "a technical moat", "weight_shift": {"momentum": 0.05}},
        {"label": "Distribution or community edge", "adds_keywords": ["community", "marketplace", "viral"], "must_have": "a distribution edge", "weight_shift": {"momentum": 0.05}},
        {"label": "Regulatory or compliance wedge", "adds_keywords": ["compliance", "licence", "regulated"], "must_have": "a regulatory wedge", "weight_shift": {"verification": 0.05}}]}
    if stage in ("idea", "pre-seed"):
        q2 = {"id": "q2", "text": "Before product-market fit, which demand signal do you trust most?", "options": [
            {"label": "Users on a waitlist or early access", "adds_keywords": ["waitlist", "early access"], "weight_shift": {"momentum": 0.05}},
            {"label": "Design partners or paid pilots", "adds_keywords": ["pilot", "design partner"], "must_have": "design partners or pilots", "weight_shift": {"verification": 0.05}},
            {"label": "Open-source adoption", "adds_keywords": ["open source", "github"], "weight_shift": {"momentum": 0.05}}]}
    else:
        q2 = {"id": "q2", "text": "Which traction proof matters most at this stage?", "options": [
            {"label": "Paying customers", "adds_keywords": ["pricing", "customers", "case study"], "must_have": "paying customers", "weight_shift": {"verification": 0.05}},
            {"label": "Fast usage growth", "adds_keywords": ["users", "growth"], "weight_shift": {"momentum": 0.10}},
            {"label": "Enterprise or regulated pilots", "adds_keywords": ["enterprise", "soc 2", "compliance"], "must_have": "enterprise or regulated pilots"}]}
    q3 = {"id": "q3", "text": "How under-the-radar should the companies be?", "options": [
        {"label": "Unknown to press and databases", "weight_shift": {"stealth": 0.10}},
        {"label": "Some coverage is fine", "weight_shift": {"stealth": -0.05, "fit": 0.05}}]}
    long_words = [w for w in words if len(w) >= 5][:3]
    extra = []
    for w in words:
        if w.endswith("tech") and len(w) > 7:
            extra += [f"{w[:-4]} tech", w[:-4]]
    return {"keywords": {"core": _dedupe([industry] + extra + long_words)[:8], "adjacent": [], "negative": DEFAULT_NEG},
            "questions": [q1, q2, q3]}


def validate_design(d):
    """Return a clean design or None. Drops options that do not change the search."""
    if not isinstance(d, dict) or not isinstance(d.get("keywords"), dict):
        return None
    kw = d["keywords"]
    clean_kw = {k: _dedupe(kw.get(k, []) if isinstance(kw.get(k, []), list) else [])[:14] for k in ("core", "adjacent", "negative")}
    if not clean_kw["core"]:
        return None
    if not clean_kw["negative"]:
        clean_kw["negative"] = DEFAULT_NEG
    questions = []
    for q in (d.get("questions") or [])[:3]:
        opts = []
        for o in (q.get("options") or [])[:4]:
            ws = {k: max(-0.15, min(0.15, float(v))) for k, v in (o.get("weight_shift") or {}).items()
                  if k in BASE_WEIGHTS and isinstance(v, (int, float))}
            o2 = {"label": str(o.get("label", "")).strip(), "adds_keywords": _dedupe(o.get("adds_keywords") or []),
                  "anti_signals": _dedupe(o.get("anti_signals") or []), "must_have": str(o.get("must_have") or "").strip(),
                  "weight_shift": {k: v for k, v in ws.items() if v}}
            if o2["label"] and (o2["adds_keywords"] or o2["anti_signals"] or o2["must_have"] or o2["weight_shift"]):
                opts.append(o2)
        if q.get("text") and len(opts) >= 2:
            questions.append({"id": q.get("id") or f"q{len(questions)+1}", "text": q["text"], "options": opts})
    if not questions:
        return None
    return {"keywords": clean_kw, "questions": questions}


def design(industry, stage, location):
    raw = llm.complete_json(PROMPT.format(industry=industry, stage=stage, location=location))
    d = validate_design(raw)
    if d:
        return d, llm.provider(), "ok"
    if llm.provider() is None:
        why = "no LLM key visible to this run (check the secret is named exactly GEMINI_API_KEY)"
    elif raw is None:
        why = f"LLM call failed: {llm.LAST_ERROR}"
    else:
        why = "LLM output rejected: no valid keywords or no MCQ options that change the search"
    return validate_design(fallback_design(industry, stage)), "fallback", why


def ask(questions, answers=None):
    """answers: list of 1-based option numbers. Interactive when None and stdin is a terminal."""
    chosen = []
    for i, q in enumerate(questions):
        if answers and i < len(answers):
            pick = answers[i]
        elif sys.stdin.isatty():
            print(f"\n{q['text']}")
            for j, o in enumerate(q["options"], 1):
                print(f"  {j}. {o['label']}")
            raw = input("Your pick: ").strip()
            pick = int(raw) if raw.isdigit() else 1
        else:
            pick = 1
        chosen.append(max(1, min(len(q["options"]), int(pick))))
    return chosen


def build(industry, stage, location, dsn, answers, provider, llm_status=""):
    kws = {k: list(v) for k, v in dsn["keywords"].items()}
    search_terms = list(kws["core"])[:6]
    anti, must, shift = [], [], dict.fromkeys(BASE_WEIGHTS, 0.0)
    for q, a in zip(dsn["questions"], answers):
        o = q["options"][a - 1]
        kws["core"] = _dedupe(kws["core"] + o["adds_keywords"])
        anti += o["anti_signals"]
        if o["must_have"]:
            must.append(o["must_have"])
        for k, v in o["weight_shift"].items():
            shift[k] += v
    w = {k: max(0.05, BASE_WEIGHTS[k] + shift[k]) for k in BASE_WEIGHTS}
    total = sum(w.values())
    w = {k: round(v / total, 3) for k, v in w.items()}
    g = geo.resolve(location)
    where = f" in {location}" if location and g["country"] != "GLOBAL" and location.lower() != "global" else ""
    stmt = (f"{stage.title()} {industry} startups{where} showing {', '.join(must) or 'verifiable early traction'}, "
            f"found through indirect signals before wide press coverage.")
    return {"id": f"{dt.date.today()}-{re.sub(r'[^a-z0-9]+', '-', industry.lower()).strip('-')}-{stage}",
            "created": dt.date.today().isoformat(), "inputs": {"industry": industry, "stage": stage, "location": location},
            "geo": g, "statement": stmt, "keywords": kws, "search_terms": search_terms, "must_have": must, "anti_signals": _dedupe(anti),
            "weights": w, "design_provider": provider, "llm_status": llm_status,
            "qa": [{"question": q["text"], "answer": q["options"][a - 1]["label"]} for q, a in zip(dsn["questions"], answers)]}


def save(thesis, outdir):
    p = pathlib.Path(outdir)
    p.mkdir(parents=True, exist_ok=True)
    (p / "thesis.json").write_text(json.dumps(thesis, indent=2))
    return p / "thesis.json"
