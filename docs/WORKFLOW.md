# vc-scout v2: end-to-end workflow and eval plan

Status: DESIGN (no code yet). Review, change, then build milestone by milestone.

## 0. Positioning (honest)
We will NOT beat Harmonic-class tools on breadth, freshness at scale, headcount/funding graphs or team data.
Those are their moat. We aim to beat them, measurably, on:
1. Verified precision (is it a real operating startup?)
2. Thesis-conditioned long-tail discovery in a chosen geography
3. Lead time on pre-seed/under-the-radar companies
4. Auditability (every claim links to evidence)
Claims are only made if the eval harness (section 8) supports them.

## 1. Inputs
| Input | Form | Notes |
|---|---|---|
| Industry | taxonomy pick or free text | all industries; mapped to a sector taxonomy |
| Stage | idea / pre-seed / seed / Series A | selects the source set (section 3) |
| Location | free text (country, state, city) | geocoded to country + aliases; selects registries and languages |
| MCQ answers | max 3 questions | generated per industry+stage (section 2) |

## 2. Thesis builder (LLM: Gemini, schema-validated JSON)
Step A: from (industry, stage, location) generate:
- keyword sets: core, adjacent, negative (words that signal non-startups)
- up to 3 MCQs, each 3 to 4 options, industry- and stage-specific
- rule: a question is only allowed if each option changes search behavior (keywords, weights, sources or filters). Questions that do not change the search are rejected and regenerated.
Step B: after the answers, produce a Thesis object:
```json
{
  "statement": "...",
  "must_have": ["..."], "nice_to_have": ["..."], "anti_signals": ["..."],
  "keywords": {"core": [], "adjacent": [], "negative": []},
  "weights": {"fit": 0.4, "verification": 0.3, "momentum": 0.2, "stealth": 0.1},
  "source_plan": ["github", "producthunt", "..."]
}
```
The thesis is saved to `runs/<id>/thesis.json` so every result is reproducible.

## 3. Source planner (stage x geography x industry)
| Stage | Primary sources | Why |
|---|---|---|
| Idea / pre-seed | GitHub, Hugging Face, HN Show, Devpost, university incubator cohorts, grants (SBIR, BIRAC, Innovate UK), trademark/patent filings, job posts, hackathon winners | intent signals before any registry entry |
| Seed | Product Hunt, YC/Techstars/Antler/EF batch pages, Startup India/DPIIT list, SEC Form D, Companies House, app/extension stores, regulatory sandboxes | launches and registrations |
| Series A | press feeds, EDGAR, registries, changelogs, pricing pages, hiring pages | traction and reputation |
Geography selects registries from `config/registries.yaml` (country -> registries, languages, access method).
Industry selects sector registries (ClinicalTrials.gov, CDSCO, FDA 510(k), FSSAI, BIS, etc.).
Every source declares: access method, rate limit, ToS risk, cost, freshness. Sources with ToS risk are off by default.

## 4. Pipeline
```
Inputs -> Thesis builder -> Source planner
   -> Collectors (parallel, cached, rate-limited)  -> RawSignal[]
   -> Entity resolution                            -> Company[]
   -> Verification engine                          -> tier + confidence + evidence
   -> Stealth + momentum                           -> radar and delta scores
   -> Thesis-fit scoring (rubric, cited)           -> fit score
   -> Rank + memo (evidence-linked)                -> digest
   -> Human feedback (interested / pass / why)     -> weight nudges
```

### 4.1 Collectors
Common interface: `fetch(thesis, geo) -> list[RawSignal]`, where a RawSignal carries source, URL, timestamp,
raw fields and a provenance id. All responses are cached in SQLite (`data/cache.db`) with TTLs.

### 4.2 Entity resolution (the hard part)
- Primary key: normalized registrable domain.
- Secondary keys: legal name + country, GitHub org, Product Hunt slug, trademark applicant.
- Merge rules: exact domain match -> merge; name match + country + same founder handle -> merge; fuzzy-only matches go to a review queue, never auto-merged.
- Every merged Company keeps the full list of RawSignals (provenance).

### 4.3 Verification engine (rules decide the tier, the LLM only classifies page text with quoted evidence)
Evidence checks: live domain and TLS age, product/pricing page present, team/about page, recent activity (changelog, commits, posts), registry match, hiring page or job post, independent corroboration (count of distinct source families).
Anti-evidence: parked domain, tutorial/template/portfolio content, student-project markers, no activity in 90 days, archived repo.
| Tier | Rule |
|---|---|
| Verified-operating | registry or equivalent entity match AND live product evidence AND recent activity AND >= 2 independent source families |
| Likely | live product + team evidence + activity, but no entity match |
| Unverified | single-source listing. Shown in a separate section, never ranked above higher tiers |
Each tier assignment stores its evidence list so it can be audited.

### 4.4 Stealth and momentum
- Stealth index: inverse of external coverage (press mentions, aggregator presence, follower counts, PH rank). Higher means more under the radar.
- Momentum: weekly snapshots stored in `data/snapshots/`; deltas (commits, stars, job posts, site changes) are computed from our own history. This longitudinal data is something static databases do not give us.

### 4.5 Thesis-fit scoring
LLM rubric scores each `must_have` / `nice_to_have` / `anti_signal` with a required evidence quote and URL. A criterion with no quote scores zero.
Final rank = weighted(fit, verification confidence, momentum, stealth) using thesis weights.

### 4.6 Memo
Skepticism-first one-pager: one-liner, why now, builder/team evidence, risks ("what would make me wrong"), 5 questions for the founder, verdict. Every factual claim must carry a source link, or it is labelled "(inferred)".

### 4.7 Feedback loop
User marks each result Interested / Pass (+ reason tag). A simple logistic update nudges weights and keyword lists per user. Stored in `data/feedback.jsonl`.

## 5. Interface (decision needed)
Phase 1: CLI (`python -m scout run --industry ... --stage ... --location ...`) with interactive MCQs.
Phase 2: small web UI (Streamlit or a hosted page) so MCQs and the digest are clickable.
GitHub Actions stays for the scheduled weekly refresh of saved theses.

## 6. Constraints and how we respect them
| Constraint | Handling |
|---|---|
| No paid data | free APIs and public pages only; paid sources are plug-in adapters, off by default |
| GitHub 5,000 req/h (authenticated) | cache, conditional requests, per-run budget |
| Gemini free-tier limits | batch prompts, cache LLM outputs by content hash, cap memos per run |
| Actions 6 h job limit, ephemeral disk | checkpoint to `data/`, resumable runs |
| robots.txt and ToS | respect robots, polite crawl delay, no LinkedIn scraping, ToS-risk sources default off |
| Personal data (DPDP, GDPR) | store only public, necessary fields; no personal contact scraping |
| Hallucination risk | schema-validated JSON, quote-or-zero rule, claims tied to sources |
| Legal entity data not bulk-free in many countries | registry adapters per country, manual-lookup links where no API exists |

## 7. Milestones
- M1: schemas, thesis builder + MCQ generator, `registries.yaml`
- M2: collectors (GitHub, Product Hunt, HN, EDGAR, Companies House, Startup India list)
- M3: entity resolution + verification engine
- M4: stealth/momentum + thesis-fit scoring + memo
- M5: eval harness (section 8) with a frozen benchmark
- M6: feedback loop + web UI

## 8. Eval plan (where we can credibly win)
| Eval | Method | Baseline | Target |
|---|---|---|---|
| E1 Verified precision | Manually label 100 sampled Verified-operating results as real operating startup or not | raw GitHub topic search; keyword-only listing | >= 90% precision vs baseline's likely 10 to 30% |
| E2 Lead time (backtest) | For known startups with a first institutional round in a past window, compute the earliest date our rules would have flagged them from public timestamps (first commit, PH launch, incorporation, trademark) vs the funding/press date | press/funding-feed detection date | median lead time > 60 days |
| E3 Under-the-radar rate | % of Verified results with low external coverage (no major-press or aggregator listing) | typical database top-N | >= 50% |
| E4 Thesis relevance | Blind human rating of top-10 per thesis; precision@10 and nDCG@10 | keyword search; LLM-only without verification | beat both baselines |
| E5 Auditability | % of memo claims with a working source link | n/a | 100% |
| E6 Long-tail geography | Verified companies found per thesis in a tier-2/3 city | open-web baseline | report as a count; no head-to-head claim |
Notes:
- A direct head-to-head against Harmonic needs access to Harmonic (trial, demo or a seat). Without it we compare against public baselines only and say so.
- Beware ground-truth leakage in E2: only use timestamps that existed before the funding date.
- Freeze the benchmark set before tuning. Do not tune on it.

## 9. Decisions
1. Interface: CLI first, web UI later (decided).
2. First registry countries: US, UK, India (decided).
3. Benchmark: draft in `benchmark/candidates.csv`, pending approval. Needs negative controls (look-alike projects that never raised) to avoid survivorship bias, plus non-software examples. See `docs/TOOLBOX.md` for free tools.

## 10. Implementation status (updated)
| Milestone | Status |
|---|---|
| M1 thesis builder + MCQs + registries/source config | built; offline-tested; LLM path untested live |
| M2 collectors: GitHub (live-tested), HN, Product Hunt, Companies House | built; HN/PH/CH endpoint shapes unverified live |
| M3 entity resolution + verification tiers | built; tier logic unit-tested; site/job-board/registry checks untested live |
| M4 stealth, momentum snapshots, scoring, memos | built; unit-tested |
| M5 eval harness (E1 to E6) | NOT built; needs approved benchmark + negative controls |
| M6 feedback loop + web UI | NOT built |
Known gaps: SEC Form D check is best-effort; ecosyste.ms endpoint shape is inferred; no fuzzy review UI; Gemini-designed MCQs not yet reviewed on real runs.
