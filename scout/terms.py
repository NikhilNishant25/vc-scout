"""Turn one specific search phrase into progressively broader variants. Specific LLM phrases rarely match exactly."""
from __future__ import annotations
import re


def variants(term):
    words = [w for w in re.split(r"\s+", term.strip()) if w]
    out = [" ".join(words)]
    if len(words) >= 3:
        out += [" ".join(words[:2]), " ".join(words[-2:])]
    return list(dict.fromkeys(v for v in out if v))
