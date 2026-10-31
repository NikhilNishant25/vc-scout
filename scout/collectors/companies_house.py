from __future__ import annotations
import datetime as dt, os
from .. import http
from ..models import RawSignal

SIC = {("software", "ai", "saas", "app", "platform", "agent", "data", "cloud", "developer"): "62012,62020,62090,63110",
       ("biotech", "health", "pharma", "medical", "clinical"): "72110,21100,86900",
       ("fintech", "payments", "finance", "insurance"): "64999,66190,66290",
       ("hardware", "robotics", "device", "manufacturing", "space"): "26200,28990,30300"}


def _sic_for(thesis):
    text = " ".join(thesis["keywords"]["core"]).lower()
    for words, codes in SIC.items():
        if any(w in text for w in words):
            return codes
    return None


def collect(thesis):
    days = {"pre-seed": 365, "seed": 900, "series-a": 1500}.get(thesis["inputs"]["stage"], 365)
    params = {"incorporated_from": (dt.date.today() - dt.timedelta(days=days)).isoformat(), "company_status": "active", "size": 100}
    sic = _sic_for(thesis)
    if sic:
        params["sic_codes"] = sic
    else:
        params["company_name_includes"] = thesis["keywords"]["core"][0].split()[0]
    r = http.request("GET", "https://api.company-information.service.gov.uk/advanced-search/companies",
                     params=params, auth=(os.environ["COMPANIES_HOUSE_KEY"], ""), ttl=24 * 3600)
    out = []
    for it in r.get("items", []):
        num = it.get("company_number")
        out.append(RawSignal("companies_house", "incorporation", it.get("company_name", "").title(),
                             f"https://find-and-update.company-information.service.gov.uk/company/{num}", None,
                             it.get("date_of_creation"), {"company_number": num, "sic_codes": it.get("sic_codes"),
                                                        "status": it.get("company_status")}))
    return out
