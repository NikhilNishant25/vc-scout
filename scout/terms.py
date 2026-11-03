"""Turn one specific search phrase into progressively broader variants. Specific LLM phrases rarely match exactly."""
from __future__ import annotations
import re


def variants(term):
    words = [w for w in re.split(r"\s+", term.strip()) if w]
    out = [" ".join(words)]
    if len(words) >= 3:
        out += [" ".join(words[:2]), " ".join(words[-2:])]
    return list(dict.fromkeys(v for v in out if v))


STOP = {"and", "or", "the", "for", "with", "next", "gen", "based", "using", "new"}


def phrase_score(phrase, blob):
    """1.0 exact phrase; 0.6 all significant words present; 0.3 all but one (needs >=3 words); else 0."""
    if re.search(rf"\b{re.escape(phrase)}", blob):
        return 1.0
    words = [w for w in re.findall(r"[a-z0-9]+", phrase) if w not in STOP and len(w) > 2]
    if len(words) < 2:
        return 0.0
    hit = sum(re.search(rf"\b{re.escape(w)}", blob) is not None for w in words)
    if hit == len(words):
        return 0.6
    return 0.3 if len(words) >= 3 and hit == len(words) - 1 else 0.0
