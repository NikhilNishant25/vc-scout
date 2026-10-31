from __future__ import annotations
import datetime as dt, os
from .. import http
from ..models import RawSignal
from ..resolve import reg_domain

QUERY = """query($cursor:String,$after:DateTime){posts(first:50,order:NEWEST,postedAfter:$after,after:$cursor){
pageInfo{endCursor hasNextPage} edges{node{name tagline description website url votesCount createdAt}}}}"""


def collect(thesis):
    days = {"pre-seed": 120, "seed": 240, "series-a": 365}.get(thesis["inputs"]["stage"], 120)
    after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    kws = thesis["keywords"]["core"] + thesis["keywords"]["adjacent"]
    out, cursor = [], None
    for _ in range(8):
        r = http.request("POST", "https://api.producthunt.com/v2/api/graphql",
                         headers={"Authorization": f"Bearer {os.environ['PRODUCTHUNT_TOKEN']}"},
                         json_body={"query": QUERY, "variables": {"cursor": cursor, "after": after}}, ttl=6 * 3600)
        posts = r["data"]["posts"]
        for e in posts["edges"]:
            n = e["node"]
            blob = f"{n['name']} {n.get('tagline') or ''} {n.get('description') or ''}".lower()
            hit = [k for k in kws if k in blob]
            if not hit:
                continue
            landing = http.final_url(n["website"]) if n.get("website") else None
            out.append(RawSignal("producthunt", "launch", n["name"], n["url"], reg_domain(landing), n["createdAt"],
                                 {"tagline": n.get("tagline"), "description": n.get("description"),
                                  "votes": n.get("votesCount") or 0, "matched": hit[:3]}))
        if not posts["pageInfo"]["hasNextPage"]:
            break
        cursor = posts["pageInfo"]["endCursor"]
    return out
