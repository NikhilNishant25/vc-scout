from __future__ import annotations
import argparse, datetime as dt, glob, json, pathlib
from . import known, pipeline, thesis


def _answers(s):
    return [int(x) for x in s.split(",") if x.strip().isdigit()] if s else None


def cmd_thesis(a):
    dsn, prov, status = thesis.design(a.industry, a.stage, a.location)
    ans = thesis.ask(dsn["questions"], _answers(a.answers))
    t = thesis.build(a.industry, a.stage, a.location, dsn, ans, prov, status)
    p = thesis.save(t, pathlib.Path("runs") / t["id"])
    print(f"thesis saved: {p}\n{t['statement']}\nweights: {t['weights']}  (design: {prov}; {status})")
    return t


def cmd_run(a):
    t = json.loads(pathlib.Path(a.thesis).read_text())
    pipeline.run(t, pathlib.Path(a.thesis).parent, a.top, a.memos, a.verify_top)


def cmd_go(a):
    t = cmd_thesis(a)
    pipeline.run(t, pathlib.Path("runs") / t["id"], a.top, a.memos, a.verify_top)


def cmd_rerun_all(a):
    for f in sorted(glob.glob("theses/*.json")):
        t = json.loads(pathlib.Path(f).read_text())
        out = pathlib.Path("runs") / f"{dt.date.today()}-{pathlib.Path(f).stem}"
        out.mkdir(parents=True, exist_ok=True)
        pipeline.run(t, out, a.top, a.memos, a.verify_top)


def cmd_llm_check(a):
    from . import llm
    print("\n".join(llm.check()))


def cmd_api_check(a):
    from . import apicheck
    print("\n".join(apicheck.run()))


def main():
    p = argparse.ArgumentParser(prog="scout")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, spec=True):
        if spec:
            sp.add_argument("--industry", required=True)
            sp.add_argument("--stage", required=True, choices=thesis.STAGES)
            sp.add_argument("--location", default="")
            sp.add_argument("--answers", default="", help="e.g. 1,2,1 (skips the prompts)")
        sp.add_argument("--top", type=int, default=15)
        sp.add_argument("--memos", type=int, default=5)
        sp.add_argument("--verify-top", type=int, default=40)

    t = sub.add_parser("thesis"); common(t); t.set_defaults(fn=cmd_thesis)
    g = sub.add_parser("go"); common(g); g.set_defaults(fn=cmd_go)
    r = sub.add_parser("run"); r.add_argument("--thesis", required=True); common(r, spec=False); r.set_defaults(fn=cmd_run)
    ra = sub.add_parser("rerun-all"); common(ra, spec=False); ra.set_defaults(fn=cmd_rerun_all)
    ac = sub.add_parser("api-check"); ac.set_defaults(fn=cmd_api_check)
    lc = sub.add_parser("llm-check"); lc.set_defaults(fn=cmd_llm_check)
    k = sub.add_parser("refresh-known"); k.set_defaults(fn=lambda a: print(f"known domains: {known.refresh()}"))
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
