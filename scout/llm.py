"""Provider-agnostic LLM calls. Order: Anthropic, Gemini (free AI Studio key), OpenRouter (free models).
With no key set, callers get None and must use their deterministic fallback."""
from __future__ import annotations
import json, os, re
from . import http

MONTH = 30 * 86400
LAST_ERROR = None


def provider():
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    return None


def _gemini(prompt, json_mode):
    model = os.getenv("SCOUT_GEMINI_MODEL", "gemini-2.5-flash")
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if json_mode:
        body["generationConfig"] = {"responseMimeType": "application/json"}
    r = http.request("POST", f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                     headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, json_body=body, ttl=MONTH, timeout=90)
    return "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])


def _openrouter(prompt, json_mode):
    model = os.getenv("SCOUT_OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    r = http.request("POST", "https://openrouter.ai/api/v1/chat/completions",
                     headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                     json_body={"model": model, "messages": [{"role": "user", "content": prompt}]}, ttl=MONTH, timeout=90)
    return r["choices"][0]["message"]["content"]


def _anthropic(prompt, json_mode):
    import anthropic
    c = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    m = c.messages.create(model=os.getenv("SCOUT_MODEL", "claude-sonnet-5-5"), max_tokens=2000,
                          messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in m.content if b.type == "text")


def complete(prompt, json_mode=False):
    p = provider()
    if p is None:
        return None
    return {"anthropic": _anthropic, "gemini": _gemini, "openrouter": _openrouter}[p](prompt, json_mode)


def extract_json(text):
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(text[a:b + 1])
        except ValueError:
            return None
    return None


def complete_json(prompt):
    """Returns parsed JSON or None. One repair attempt, never raises."""
    global LAST_ERROR
    LAST_ERROR = None
    try:
        out = extract_json(complete(prompt, json_mode=True))
        if out is None and provider():
            out = extract_json(complete(prompt + "\n\nReturn ONLY valid JSON, no prose.", json_mode=True))
        if out is None and provider():
            LAST_ERROR = "model replied but not with valid JSON"
        return out
    except Exception as e:  # network/quota/bad key: caller falls back
        LAST_ERROR = str(e)[:200]
        print(f"[warn] LLM call failed: {e}")
        return None
