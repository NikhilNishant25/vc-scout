from __future__ import annotations
import dataclasses, json, pathlib, time
import yaml
from . import known as known_mod, llm, memo, planner, rank, resolve, verify
from .collectors import companies_house, ecosystems, github, hn, producthunt

COLLECTORS = {"ecosystems": ecosystems, "github": github, "hn": hn, "producthunt": producthunt, "companies_house": companies_house}
REG = pathlib.Path(__file__).resolve().parent.parent / "config" / "registries.yaml"


def _summary(c):
    ev, bits = c.evidence, []
    site = ev.get("site", {})
    bits.append("site live" if site.get("live") else f"site: {str(site.get('reason', 'n/a'))[:50]}")
    if site.get("product"):
        bits.append("product page")
    if ev.get("hiring"):
        bits.append(f"hiring {ev['hiring']['count']} ({ev['hiring']['board']})")
    if ev.get("registry", {}).get("matched"):
        bits.append(f"registry: {ev['registry']['type']}")
    sg = ev.get("signals", {})
    if sg.get("accelerator") or sg.get("funding"):
        bits.append("claims: " + ", ".join((sg.get("accelerator") or []) + (sg.get("funding") or []))[:60])
    if sg.get("customers"):
        bits.append("customers/partners mentioned")
    g = ev.get("github", {})
    if g:
        bits.append("github data unavailable" if g.get("commits_30d") is None else f"commits30d {g['commits_30d']}")
    return "; ".join(bits)


def _clean(c):
    d = dataclasses.asdict(c)
    for s in d["signals"]:
        s["data"].pop("repo", None)
    d["evidence"].get("site", {}).pop("text", None)
    return d


def run(thesis, outdir, top=15, memos=5, verify_top=40):
    out = pathlib.Path(outdir)
    (out / "memos").mkdir(parents=True, exist_ok=True)
    plan = planner.plan(thesis)
    status, signals = {}, []
    for p in plan:
        if not p["enabled"]:
            status[p["source"]] = {"status": "skipped", "reason": p["reason"]}
            continue
        try:
            got = COLLECTORS[p["source"]].collect(thesis)
            signals += got
            status[p["source"]] = {"status": "ok", "signals": len(got), "maturity": p["status"]}
        except Exception as e:
            status[p["source"]] = {"status": "failed", "error": str(e)[:200], "maturity": p["status"]}
            print(f"[warn] collector {p['source']} failed: {e}")
    companies, review = resolve.resolve(signals)
    known = known_mod.load()
    companies.sort(key=lambda c: -rank.prelim(c, thesis, known))
    to_verify = companies[:verify_top]
    for c in to_verify:
        try:
            verify.verify(c, thesis)
        except Exception as e:
            c.flags.append(f"verify-error:{str(e)[:60]}")
        rank.score(c, thesis, known)
        rank.save_snapshot(c)
    for c in to_verify:
        if c.scores.get("fit", 0) < 0.1 and "off-thesis" not in c.flags:
            c.flags.append("off-thesis")
    DROP = ("negative-keyword", "off-thesis", "site-name-mismatch", "parked", "archived")
    filtered = [c for c in to_verify if any(f.startswith(DROP) for f in c.flags)]
    keep = [c for c in to_verify if c not in filtered]
    ranked = rank.order(keep)[:top]
    for i, c in enumerate(ranked[:memos]):
        if c.tier != "Unverified":
            (out / "memos" / f"{i+1:02d}-{c.id}.md").write_text(memo.write(c, thesis))
            if llm.provider() == "gemini":
                time.sleep(6)  # stay under free-tier requests-per-minute limits
    (out / "candidates.json").write_text(json.dumps([_clean(c) for c in ranked], indent=2, default=str))
    report = {"thesis_id": thesis["id"], "sources": status, "signals": len(signals), "companies": len(companies),
              "verified_attempted": len(to_verify), "filtered_out": len(filtered), "llm_status": thesis.get("llm_status"), "review_queue": review,
              "tiers": {t: sum(c.tier == t for c in to_verify) for t in rank.TIER}}
    (out / "run_report.json").write_text(json.dumps(report, indent=2))
    reg = yaml.safe_load(REG.read_text()).get(thesis["geo"]["country"], {})
    L = [f"# Scout digest: {thesis['id']}", "", f"**Thesis:** {thesis['statement']}", "",
         f"**Thesis design:** {thesis.get('design_provider')} ({thesis.get('llm_status', '')})", "",
         "## Sources", "| Source | Status | Detail |", "|---|---|---|"]
    for k, v in status.items():
        L.append(f"| {k} | {v['status']} | {v.get('signals', v.get('reason', v.get('error', '')))} |")
    L += ["", f"Companies found: {len(companies)}. Verified-attempted: {len(to_verify)}. Tiers: {report['tiers']}", "",
          "## Ranked (tier first, then score)", "| # | Company | Tier | Score | Conf | Domain | Evidence | Flags |", "|---|---|---|---|---|---|---|---|"]
    for i, c in enumerate(ranked, 1):
        L.append(f"| {i} | {c.name} | {c.tier} | {c.rank_score} | {c.confidence} | {', '.join(c.domains[:1])} | {_summary(c)} | {', '.join(c.flags)} |")
    if filtered:
        L += ["", "## Filtered out (checked, rejected)", "| Company | Why |", "|---|---|"]
        L += [f"| {c.name} | {', '.join(f for f in c.flags if f.startswith(DROP))} |" for c in filtered]
    if reg.get("access", "").startswith("manual"):
        L += ["", f"Registry for {thesis['geo']['country']}: no free API. Check legal entities manually: {reg['link']}"]
    if review:
        L += ["", "## Possible duplicates (not merged)"] + [f"- {r['a']} ~ {r['b']} ({r['ratio']})" for r in review]
    (out / "digest.md").write_text("\n".join(L) + "\n")
    print(f"wrote {out}/digest.md ({len(ranked)} ranked, tiers {report['tiers']})")
    return report
