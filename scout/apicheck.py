"""Endpoint probes against known-real examples. Run via the 'diagnostics' workflow; output goes to runs/api-check.txt.
Never prints secrets. Each probe reports WORKS / HTTP status / shape so unverified integrations can be fixed from facts."""
from __future__ import annotations
import os, re
from . import http


def _try(name, fn):
    try:
        return f"{name}: {fn()}"
    except http.HttpError as e:
        return f"{name}: HTTP {e.code} {e.body[:160]}"
    except Exception as e:
        return f"{name}: ERROR {str(e)[:200]}"


def _keys(d, wanted):
    return "keys present=" + ",".join(k for k in wanted if k in d) + " | missing=" + ",".join(k for k in wanted if k not in d)


def run():
    L = []
    g = {}
    if os.getenv("GITHUB_TOKEN"):
        g = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"}

    def gh_rate():
        r = http.request("GET", "https://api.github.com/rate_limit", headers=g, ttl=0, retries=0)["resources"]
        return f"core {r['core']['remaining']}/{r['core']['limit']}, search {r['search']['remaining']}/{r['search']['limit']}"
    L.append(_try("github rate limit", gh_rate))

    L.append(_try("hn algolia", lambda: f"{len(http.request('GET', 'https://hn.algolia.com/api/v1/search', params={'query': 'agent', 'tags': 'show_hn', 'hitsPerPage': 3}, ttl=0, retries=0)['hits'])} hits"))

    # ecosyste.ms: package record (used for adoption evidence) and the OpenAPI spec (to find the real reverse-dependency endpoints)
    def eco_pkg():
        r = http.request("GET", "https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages/react", ttl=0, retries=0)
        return "WORKS; " + _keys(r, ["repository_url", "dependent_repos_count", "dependent_packages_count", "downloads", "funding_links"])
    L.append(_try("ecosyste.ms package (react)", eco_pkg))

    def eco_spec():
        r = http.request("GET", "https://packages.ecosyste.ms/docs/api/v1/openapi.yaml", text=True, ttl=0, retries=0)
        paths = sorted(set(re.findall(r"(/[A-Za-z0-9_{}/.\-]*dependent[A-Za-z0-9_{}/.\-]*)", r["text"])))
        return f"HTTP {r['status']}; paths mentioning 'dependent': {paths[:12]}"
    L.append(_try("ecosyste.ms openapi spec", eco_spec))

    def eco_dep():
        r = http.request("GET", "https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages/react/dependent_packages", params={"per_page": 2}, ttl=0, retries=0)
        return f"WORKS; type={type(r).__name__}; first item keys={sorted(r[0].keys())[:10] if isinstance(r, list) and r else r}"
    L.append(_try("ecosyste.ms dependent_packages (guess)", eco_dep))

    def repos_eco():
        r = http.request("GET", "https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/facebook%2Freact", ttl=0, retries=0)
        return "WORKS; " + _keys(r, ["full_name", "stargazers_count", "pushed_at", "owner", "topics"])
    L.append(_try("repos.ecosyste.ms repo (facebook/react)", repos_eco))

    # job boards: which public endpoints really answer, and with what
    boards = [("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{s}/jobs", ["stripe", "airbnb", "figma"], lambda j: len(j.get("jobs", []))),
              ("lever", "https://api.lever.co/v0/postings/{s}?mode=json", ["palantir", "spotify", "netflix"], lambda j: len(j) if isinstance(j, list) else -1),
              ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{s}", ["openai", "ramp", "notion"], lambda j: len(j.get("jobs", [])))]
    for name, url, slugs, cnt in boards:
        res = []
        for s in slugs:
            try:
                res.append(f"{s}={cnt(http.request('GET', url.format(s=s), ttl=0, retries=0))}")
            except http.HttpError as e:
                res.append(f"{s}=HTTP {e.code}")
            except Exception as e:
                res.append(f"{s}=ERR {str(e)[:40]}")
        L.append(f"job board {name}: " + ", ".join(res))

    L.append(_try("yc directory mirror", lambda: (lambda d: f"{len(d)} companies; first keys={sorted(d[0].keys())[:10]}")(http.request("GET", "https://yc-oss.github.io/api/companies/all.json", ttl=0, retries=0, timeout=60))))

    if os.getenv("PRODUCTHUNT_TOKEN"):
        def ph():
            q = "query{posts(first:1,order:NEWEST){edges{node{name tagline website url votesCount createdAt}}}}"
            r = http.request("POST", "https://api.producthunt.com/v2/api/graphql", headers={"Authorization": f"Bearer {os.environ['PRODUCTHUNT_TOKEN']}"}, json_body={"query": q}, ttl=0, retries=0)
            if "errors" in r:
                return f"GraphQL errors: {str(r['errors'])[:200]}"
            n = r["data"]["posts"]["edges"][0]["node"]
            return f"WORKS; node keys={sorted(n.keys())}; website sample={str(n.get('website'))[:60]}"
        L.append(_try("product hunt", ph))
    else:
        L.append("product hunt: skipped (no PRODUCTHUNT_TOKEN)")

    if os.getenv("COMPANIES_HOUSE_KEY"):
        L.append(_try("companies house search", lambda: f"WORKS; {len(http.request('GET', 'https://api.company-information.service.gov.uk/search/companies', params={'q': 'monzo', 'items_per_page': 3}, auth=(os.environ['COMPANIES_HOUSE_KEY'], ''), ttl=0, retries=0).get('items', []))} items"))
    else:
        L.append("companies house: skipped (no COMPANIES_HOUSE_KEY)")

    if os.getenv("SEC_USER_AGENT"):
        def sec():
            r = http.request("GET", "https://efts.sec.gov/LATEST/search-index", params={"q": '"OpenAI"', "forms": "D"}, headers={"User-Agent": os.environ["SEC_USER_AGENT"]}, ttl=0, retries=0)
            hits = r.get("hits", {}).get("hits", [])
            return f"WORKS; {len(hits)} hits; source keys={sorted(hits[0].get('_source', {}).keys())[:8] if hits else 'n/a'}"
        L.append(_try("sec edgar full-text", sec))
    else:
        L.append("sec edgar: skipped (no SEC_USER_AGENT secret)")

    # candidates for later milestones (evals, discovery)
    L.append(_try("hugging face api", lambda: f"HTTP 200; {len(http.request('GET', 'https://huggingface.co/api/models', params={'limit': 2}, ttl=0, retries=0))} models"))
    L.append(_try("wayback cdx", lambda: f"rows={len(http.request('GET', 'https://web.archive.org/cdx/search/cdx', params={'url': 'openai.com', 'limit': 2, 'output': 'json'}, ttl=0, retries=0, timeout=60))}"))
    L.append(_try("gh archive file", lambda: f"HTTP {http.request('GET', 'https://data.gharchive.org/2026-01-01-0.json.gz', text=True, ttl=0, retries=0, timeout=60)['status']} (first bytes only)"))
    return L
