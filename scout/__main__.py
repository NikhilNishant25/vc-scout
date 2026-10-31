import argparse
import datetime as dt
import pathlib
import yaml
from .github_signals import discover, enrich
from .scoring import red_flagged, score
from .memo import write_memo


def run(args):
    cfg = yaml.safe_load(open(args.config))
    repos = discover(cfg)
    print(f"discovered {len(repos)} candidates")
    ranked = []
    for repo in repos:
        e = enrich(repo)
        if red_flagged(e, cfg):
            continue
        total, sig, hits = score(e, cfg)
        ranked.append((total, e, sig, hits))
    ranked.sort(key=lambda x: x[0], reverse=True)
    ranked = ranked[: args.top]

    out = pathlib.Path("memos") / dt.date.today().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"# Scout digest {dt.date.today()}\n", "| # | Repo | Score | Stars | Commits 30d |", "|---|---|---|---|---|"]
    for i, (total, e, sig, hits) in enumerate(ranked, 1):
        r = e["repo"]
        lines.append(f"| {i} | [{r['full_name']}]({r['html_url']}) | {total} | {r['stargazers_count']} | {e['commits_30d']} |")
        if i <= args.memos:
            (out / f"{r['full_name'].replace('/', '__')}.md").write_text(write_memo(e, total, sig, hits, cfg))
    (out / "digest.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {out}/digest.md and {min(args.memos, len(ranked))} memos")


def main():
    p = argparse.ArgumentParser(prog="scout")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config", default="config/thesis.yaml")
    r.add_argument("--top", type=int, default=15)
    r.add_argument("--memos", type=int, default=5)
    r.set_defaults(fn=run)
    a = p.parse_args()
    a.fn(a)


main()
