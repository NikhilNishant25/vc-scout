from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RawSignal:
    source: str
    kind: str
    name: str
    url: str
    domain: str | None = None
    ts: str | None = None
    data: dict = field(default_factory=dict)


@dataclass
class Company:
    id: str
    name: str
    domains: list = field(default_factory=list)
    signals: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    tier: str = "Unverified"
    confidence: float = 0.0
    scores: dict = field(default_factory=dict)
    rank_score: float = 0.0
    flags: list = field(default_factory=list)
