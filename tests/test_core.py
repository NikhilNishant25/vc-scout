import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from scout import geo, rank, resolve, thesis, verify
from scout.models import Company, RawSignal


def test_geo():
    assert geo.resolve("Bengaluru")["country"] == "IN"
    assert geo.resolve("London, UK")["country"] == "UK"
    assert geo.resolve("San Francisco")["country"] == "US"
    assert geo.resolve("Lagos")["country"] == "GLOBAL"


def test_fallback_design_valid_and_effective():
    d = thesis.validate_design(thesis.fallback_design("AI agent infrastructure", "seed"))
    assert d and 1 <= len(d["questions"]) <= 3
    for q in d["questions"]:
        assert 2 <= len(q["options"]) <= 4


def test_validate_drops_options_that_change_nothing():
    d = {"keywords": {"core": ["x"], "adjacent": [], "negative": []},
         "questions": [{"text": "q", "options": [{"label": "a"}, {"label": "b"}, {"label": "c", "adds_keywords": ["k"]}]}]}
    assert thesis.validate_design(d) is None  # only 1 effective option survives -> question dropped -> no questions


def test_build_weights_normalized_and_answers_apply():
    dsn = thesis.validate_design(thesis.fallback_design("fintech", "seed"))
    t = thesis.build("fintech", "seed", "Mumbai", dsn, [3, 1, 1], "fallback")
    assert abs(sum(t["weights"].values()) - 1) < 0.01
    assert "compliance" in t["keywords"]["core"]
    assert t["geo"]["country"] == "IN"


def _s(source, name, domain=None, **data):
    return RawSignal(source, "x", name, f"https://x/{name}", domain, "2026-10-01T00:00:00Z", data)


def test_reg_domain():
    assert resolve.reg_domain("https://www.acme.co.uk/path") == "acme.co.uk"
    assert resolve.reg_domain("https://foo.github.io/x") is None
    assert resolve.reg_domain("https://github.com/a/b") is None


def test_resolution_merges_by_domain_and_repo_but_not_name_clash():
    sigs = [_s("github", "acme/agentkit", "agentkit.dev", full_name="acme/agentkit", stars=50),
            _s("hn", "AgentKit", None, github_repo="acme/agentkit", points=40),
            _s("producthunt", "AgentKit", "agentkit.dev", votes=100),
            _s("github", "other/agentkit", "different.io", full_name="other/agentkit", stars=5)]
    companies, review = resolve.resolve(sigs)
    assert len(companies) == 2
    big = max(companies, key=lambda c: len(c.signals))
    assert {s.source for s in big.signals} == {"github", "hn", "producthunt"}


def _f(**k):
    base = dict(live=True, parked=False, product=True, team=True, recent=True, hiring=False, registry=False, families=1, flags=[])
    base.update(k)
    return base


def test_tiers():
    assert verify.assess(_f(registry=True, families=2))[0] == "Verified-operating"
    assert verify.assess(_f(hiring=True, team=True, families=2))[0] == "Verified-operating"  # entity via hiring+team, 2 families
    assert verify.assess(_f())[0] == "Likely"
    assert verify.assess(_f(live=False))[0] == "Unverified"
    assert verify.assess(_f(registry=True, families=3, flags=["parked-domain"]))[0] == "Unverified"
    assert verify.assess(_f(product=False, team=False, hiring=False))[0] == "Unverified"
    assert verify.assess(_f(registry=True, families=3))[1] > verify.assess(_f())[1]


def test_unverified_never_outranks_higher_tier():
    a, b = Company("a", "A"), Company("b", "B")
    a.tier, a.rank_score = "Unverified", 0.99
    b.tier, b.rank_score = "Likely", 0.10
    assert [c.id for c in rank.order([a, b])] == ["b", "a"]


def test_stealth_known_company_is_zero():
    c = Company("a", "A", domains=["known.com"], signals=[_s("github", "x/y", stars=10)])
    assert rank.stealth(c, {"known.com"}) == 0.0
    c2 = Company("b", "B", domains=["new.io"], signals=[_s("github", "x/z", stars=10)])
    assert rank.stealth(c2, {"known.com"}) > 0.7


def test_search_terms_exclude_option_keywords():
    dsn = thesis.validate_design(thesis.fallback_design("AI agent infrastructure", "seed"))
    t = thesis.build("AI agent infrastructure", "seed", "", dsn, [1, 1, 1], "fallback")
    assert "viral" not in t["search_terms"] and "open source" not in t["search_terms"]
    assert "open source" in t["keywords"]["core"]  # still used for fit scoring


def test_unknown_commits_do_not_count_as_zero_activity_evidence():
    from scout import rank
    c = Company("a", "A", signals=[_s("github", "x/y", stars=10)])
    c.evidence = {"github": {"commits_30d": None, "age_days": 30}}
    assert 0 <= rank.momentum(c) <= 1  # no TypeError on None
