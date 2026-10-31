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


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_SKIP = ("tts", "image", "live", "audio", "transcribe", "omni", "embed", "lyria", "veo", "imagen", "robotics",
         "computer-use", "deep-research", "gemma", "aqa", "learnlm", "vision")
LAST_MODEL = None
_BAD = set()


def _version(name):
    import re
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0.0


def gemini_candidates(names):
    """Rank usable text models: newest generation first, full Flash before Flash-Lite, stable before preview."""
    ok = [n for n in names if n.startswith("gemini-") and "flash" in n and not any(x in n for x in _SKIP)]
    return sorted(ok, key=lambda n: (-_version(n), "lite" in n, "preview" in n, n))[:8]


def _gemini_models(key):
    r = http.request("GET", f"{GEMINI_BASE}/models", params={"pageSize": 200}, headers={"x-goog-api-key": key}, ttl=86400)
    names = [m["name"].removeprefix("models/") for m in r.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    return gemini_candidates(names)


def _gemini(prompt, json_mode):
    """Model names get retired (gemini-2.5-* did), so discover what this key can use and fall through the list."""
    global LAST_MODEL
    key = os.environ["GEMINI_API_KEY"]
    cands = [os.environ["SCOUT_GEMINI_MODEL"]] if os.getenv("SCOUT_GEMINI_MODEL") else []
    try:
        cands += [m for m in _gemini_models(key) if m not in cands]
    except (http.HttpError, RuntimeError) as e:
        if not cands:
            raise RuntimeError(f"could not list Gemini models for this key: {e}")
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if json_mode:
        body["generationConfig"] = {"responseMimeType": "application/json"}
    errors = []
    for model in cands:
        if model in _BAD:
            continue
        try:
            r = http.request("POST", f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                             json_body=body, ttl=MONTH, timeout=90, retries=1)
            LAST_MODEL = model
            return "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
        except http.HttpError as e:
            _BAD.add(model)
            errors.append(f"{model}: HTTP {e.code} {e.body[:140]}")
        except (RuntimeError, KeyError, IndexError) as e:
            _BAD.add(model)
            errors.append(f"{model}: {str(e)[:140]}")
    raise RuntimeError(("no Gemini model worked. " + " | ".join(errors)) if errors else "no usable Gemini model found for this key")


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
        LAST_ERROR = str(e)[:700]
        print(f"[warn] LLM call failed: {e}")
        return None


def check():
    """Diagnostics for `python -m scout llm-check`. Never prints keys."""
    lines = [f"provider: {provider()}"]
    if provider() != "gemini":
        return lines + ["(only the Gemini check is implemented; set GEMINI_API_KEY)"]
    key = os.environ["GEMINI_API_KEY"]
    try:
        r = http.request("GET", f"{GEMINI_BASE}/models", params={"pageSize": 200}, headers={"x-goog-api-key": key}, ttl=0)
        names = [m["name"].removeprefix("models/") for m in r.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        lines.append(f"models visible to this key supporting generateContent: {len(names)}")
        lines.append("all: " + ", ".join(sorted(names)))
    except http.HttpError as e:
        return lines + [f"ListModels failed: HTTP {e.code} {e.body}"]
    except RuntimeError as e:
        return lines + [f"ListModels failed: {e}"]
    for m in gemini_candidates(names):
        try:
            out = http.request("POST", f"{GEMINI_BASE}/models/{m}:generateContent", headers={"x-goog-api-key": key},
                               json_body={"contents": [{"parts": [{"text": "Reply with the single word OK"}]}]}, ttl=0, retries=0, timeout=60)
            lines.append(f"{m}: WORKS -> {out['candidates'][0]['content']['parts'][0].get('text', '')[:30]!r}")
        except http.HttpError as e:
            lines.append(f"{m}: HTTP {e.code} {e.body[:200]}")
        except Exception as e:
            lines.append(f"{m}: {str(e)[:200]}")
    return lines
