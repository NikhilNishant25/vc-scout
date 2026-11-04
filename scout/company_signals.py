"""Pre-seed-friendly 'is this a company, not a side project' signals, read from site text + README. Claims, not proof:
they raise confidence and open the 'Likely' tier; they never alone make something Verified-operating."""
from __future__ import annotations
import re

ACCEL = re.compile(r"\b(y combinator|ycombinator|yc\s?[ws]\d{2}|yc batch|techstars|antler|entrepreneur first|500 global|peak xv|"
                   r"south park commons|a16z speedrun|alchemist accelerator|pioneer fund|startup india|nasscom|t-hub)\b", re.I)
FUND = re.compile(r"\b(backed by [^.]{0,60}(?:ventures|capital|partners|fund|investors|y combinator|yc|techstars|angels?)|raised \$?[\d.,]+\s?(?:m|k|million|thousand)?|seed round|seed funding|pre-seed round|series a|"
                  r"funded by|our investors|investors include)\b", re.I)
HIRE = re.compile(r"\b(we'?re hiring|we are hiring|open roles|open positions|join our team|careers|work with us)\b", re.I)
COMM = re.compile(r"\b(pricing|book a demo|request a demo|contact sales|waitlist|early access|free trial|enterprise)\b", re.I)
LEGAL = re.compile(r"(?:©|&copy;|copyright)\s*(?:19|20)\d\d\s+[^.|\n]{0,40}?\b(inc\.?|ltd\.?|llc|gmbh|pvt\.? ltd\.?|labs|technologies|corp\.?)", re.I)
CUST = re.compile(r"\b(trusted by|used by \d[\d,+k]*\s+\w+|customers include|case stud(?:y|ies)|our customers|design partners?)\b", re.I)


def _hits(rx, text, n=3):
    return list(dict.fromkeys(m.group(0).lower() for m in rx.finditer(text)))[:n]


def company_signals(text):
    t = text or ""
    s = {"accelerator": _hits(ACCEL, t), "funding": _hits(FUND, t), "hiring_text": bool(HIRE.search(t)),
         "commercial": _hits(COMM, t), "legal_entity_text": bool(LEGAL.search(t)), "customers": _hits(CUST, t)}
    s["backed"] = bool(s["accelerator"] or s["funding"])
    return s
