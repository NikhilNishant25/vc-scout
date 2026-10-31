# vc-scout

A lightweight, opinionated sourcing agent. It does **not** try to be a database (that's Harmonic's job).
It watches GitHub for *behavioral intent* from early technical builders, scores them against your thesis,
and writes a skeptical one-page memo for the survivors.

```
discover (GitHub search by thesis topics)
   -> enrich (commit cadence, releases, external pull, commercial intent, builder obscurity)
   -> score (weights in config/thesis.yaml)
   -> memo (Claude, skepticism-first; template fallback without an API key)
   -> memos/YYYY-MM-DD/*.md + digest.md
```

See [docs/WORKFLOW.md](docs/WORKFLOW.md) for the v2 design and eval plan.

## Run

```bash
pip install -r requirements.txt
cp .env.example .env   # add GITHUB_TOKEN and ANTHROPIC_API_KEY
export $(grep -v '^#' .env | xargs)
python -m scout run --top 15 --memos 5
```

A GitHub Action (`.github/workflows/weekly.yml`) runs it every Monday and commits the digest.
`GITHUB_TOKEN` is automatic in Actions; add `ANTHROPIC_API_KEY` as a repo secret.

## LLM provider
Set **either** `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` (Google AI Studio key, free tier works). If both are set, Anthropic is used. With neither, memos are facts-only. A failed LLM call degrades to facts-only for that memo instead of crashing the run.

## Make it yours
Everything opinionated lives in `config/thesis.yaml`: topics, star band, weights, red-flag patterns,
and the thesis statement the memo is judged against. Change the angle there, not in code.

## Signals
| Signal | Why it matters |
|---|---|
| Star velocity | Pull relative to age, not total stars |
| Commit cadence (30d) | Is someone actually shipping |
| Recent release | Crossed from "project" to "product" |
| Commercial intent | Waitlist/pricing/hosted/cloud language, homepage set |
| External pull | Forks/stars ratio and issues from strangers |
| Obscurity | Low-follower owners are likelier un-sourced |
| Contributor breadth | More than one author in 30d |

Red flags (awesome-lists, tutorials, forks, thin READMEs) are filtered before scoring.

## Limits
GitHub is a partial view of a builder. Treat the score as a reason to look, never a reason to invest.
Unauthenticated API calls hit rate limits fast; use a token.
