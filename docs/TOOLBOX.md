# Free / open-source toolbox for vc-scout

Verify current limits and licences at build time; free tiers change.

## Historical data (key for leakage-free backtests)
- GH Archive (public GitHub event history; queryable via BigQuery free tier or the ClickHouse public playground): first commit, star curves, org activity over time
- Wayback Machine CDX API: when a site, pricing page or careers page first appeared
- crt.sh (Certificate Transparency): first TLS certificate date for a domain
- Common Crawl: historical web snapshots to detect new product domains
- HN via Algolia API / public dataset: Show HN timestamps

## Open data for discovery and verification
- OpenAlex, Semantic Scholar (research spinouts); PatentsView / Google Patents public data (patents)
- Wikidata, GLEIF LEI, OpenCorporates free tier (entity data); Nominatim/OpenStreetMap (geocoding)
- SEC EDGAR (Form D, full-text search), Companies House API (free key), data.gov.in and Startup India lists

## Models (cost: zero or near zero)
- Gemini free tier (current default)
- Open-weight models (Llama, Qwen, Mistral, Gemma) via Ollama locally, or free inference tiers (OpenRouter free models, Groq, Hugging Face, GitHub Models for prototyping)
- sentence-transformers (bge-small, MiniLM, e5): free local embeddings for thesis-fit and dedup
- Instructor / Outlines for schema-valid JSON from smaller models; LiteLLM to swap providers without code changes

## Extraction and matching
- Crawl4AI, Trafilatura, Playwright, Scrapy (respect robots.txt); extruct for structured page data
- tldextract, rapidfuzz, Splink (probabilistic record linkage) for entity resolution
- DuckDB / SQLite for local analytics and caching; FAISS or Chroma for local vector search

## Evals
- Inspect AI, promptfoo, DeepEval or Ragas for repeatable evals; plain pandas for precision / nDCG / lead-time metrics
