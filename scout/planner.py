from __future__ import annotations
import os, pathlib
import yaml

CFG = pathlib.Path(__file__).resolve().parent.parent / "config" / "sources.yaml"


def plan(thesis):
    stage, country = thesis["inputs"]["stage"], thesis["geo"]["country"]
    out = []
    for name, s in yaml.safe_load(CFG.read_text()).items():
        reason = None
        if stage not in s["stages"]:
            reason = f"not used at stage {stage}"
        elif "any" not in s["countries"] and country not in s["countries"]:
            reason = f"only for {','.join(s['countries'])}"
        else:
            missing = [e for e in s["needs_env"] if not os.getenv(e)]
            if missing:
                reason = f"missing env {','.join(missing)}"
            elif name == "ecosystems" and not thesis.get("anchors"):
                reason = "no anchor packages in this thesis (needs an LLM-designed thesis)"
        out.append({"source": name, "enabled": reason is None, "reason": reason or "ok", "status": s["status"]})
    return out
