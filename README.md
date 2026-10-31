# vc-scout

A command-line sourcing engine for early, under-the-radar startups. Pick an industry, a stage and a location;
it generates keywords and up to 3 industry/stage-specific MCQs, builds a thesis from your answers, collects
candidates from free sources, **verifies** they are real operating companies, ranks them, and writes
evidence-linked memos.

```bash
pip install -r requirements.txt
cp .env.example .env            # add GEMINI_API_KEY (free: https://aistudio.google.com/apikey)
export $(grep -v '^#' .env | xargs)

python -m scout go --industry "AI agent infrastructure" --stage pre-seed --location "Bengaluru"
# answer the MCQs, or skip prompts with --answers 2,1,1
```
Outputs land in `runs/<id>/`: `thesis.json`, `digest.md`, `candidates.json`, `run_report.json`, `memos/`.

Other commands: `thesis` (build only), `run --thesis runs/<id>/thesis.json`, `rerun-all` (every thesis in `theses/`),
`refresh-known` (loads the already-known company list used to score stealth).

## How it works
1. **Thesis builder** (Gemini or fallback): keywords + up to 3 MCQs; an option is only allowed if it changes search, weights or must-haves.
2. **Source planner**: stage and location choose sources; skipped sources say why in the digest.
3. **Collectors**: GitHub, Hacker News (Show HN), Product Hunt (token), Companies House (UK, key).
4. **Entity resolution**: one record per domain; fuzzy-only matches go to a review queue, never auto-merged.
5. **Verification**: live site, product page, team page, job boards (Greenhouse/Lever/Ashby), registry match, GitHub activity, package adoption (ecosyste.ms).
   Tiers: **Verified-operating**, **Likely**, **Unverified**. Unverified never outranks a higher tier.
6. **Scoring**: thesis fit, verification confidence, momentum (uses your own weekly snapshots in `data/snapshots/`), stealth.
7. **Memos**: skeptical one-pagers where every claim carries a source link or is marked inferred.

## Run in GitHub Actions
Actions tab > **scout** > Run workflow (industry, stage, location, MCQ picks). Weekly schedule re-runs every thesis in `theses/`.
Secrets: `GEMINI_API_KEY` (recommended); optional `PRODUCTHUNT_TOKEN`, `COMPANIES_HOUSE_KEY`, `SEC_USER_AGENT`.

## Honest limits
- Every collector reports `ok / failed / skipped` per run. Sources marked `experimental` in `config/sources.yaml` have endpoint shapes that were not live-verified when written.
- Without an LLM key the thesis uses a generic fallback design (weaker keywords) and memos are facts-only.
- India has no free bulk company-registry API; the digest links the manual lookup instead of claiming a registry match.
- No paid data (Harmonic, Crunchbase, PitchBook) and no LinkedIn scraping. See `docs/WORKFLOW.md` for the design and eval plan.

Tests: `pip install -r requirements-dev.txt && pytest`
