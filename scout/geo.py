"""Location text -> country code. Unknown places become GLOBAL (no registry assumptions)."""
from __future__ import annotations
import re

ALIASES = {
    "US": ["us", "usa", "united states", "america", "san francisco", "new york", "austin", "boston", "seattle",
           "los angeles", "chicago", "california", "texas", "silicon valley", "bay area"],
    "UK": ["uk", "united kingdom", "britain", "england", "scotland", "wales", "london", "manchester",
           "edinburgh", "cambridge", "oxford", "bristol", "birmingham"],
    "IN": ["india", "bengaluru", "bangalore", "mumbai", "delhi", "new delhi", "gurugram", "gurgaon", "noida",
           "hyderabad", "pune", "chennai", "kolkata", "jamshedpur", "ahmedabad", "jaipur", "kochi"],
}


def resolve(location):
    loc = (location or "").strip().lower()
    for code, names in ALIASES.items():
        for n in names:
            if re.search(rf"\b{re.escape(n)}\b", loc):
                return {"country": code, "query": location}
    return {"country": "GLOBAL", "query": location}
