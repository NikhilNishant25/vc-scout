"""HTTP with a SQLite cache, polite retries and no retry on 4xx. Every collector goes through here."""
from __future__ import annotations
import hashlib, json, os, pathlib, sqlite3, time
import requests

UA = os.getenv("SCOUT_USER_AGENT", "vc-scout/0.2 (+https://github.com/NikhilNishant25/vc-scout)")
DB = pathlib.Path(os.getenv("SCOUT_CACHE", "data/cache.db"))
_conn = None


class HttpError(RuntimeError):
    def __init__(self, code, url, body=""):
        super().__init__(f"HTTP {code} for {url}" + (f": {body}" if body else ""))
        self.code, self.body = code, body


def _err_body(r):
    try:
        j = r.json()
        return str((j.get("error") or {}).get("message") or j)[:300]
    except Exception:
        return r.text[:200]


def _db():
    global _conn
    if _conn is None:
        DB.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB)
        _conn.execute("create table if not exists kv (k text primary key, v text, ts real)")
    return _conn


def request(method, url, *, params=None, headers=None, json_body=None, auth=None,
            ttl=3600, timeout=20, text=False, retries=2):
    key = hashlib.sha256(json.dumps([method, url, params, json_body, text], sort_keys=True, default=str).encode()).hexdigest()
    if ttl:
        row = _db().execute("select v, ts from kv where k=?", (key,)).fetchone()
        if row and time.time() - row[1] < ttl:
            return json.loads(row[0])
    h = {"User-Agent": UA, **(headers or {})}
    last, last_resp = "unknown", None
    for i in range(retries + 1):
        try:
            r = requests.request(method, url, params=params, headers=h, json=json_body,
                                 auth=auth, timeout=timeout, allow_redirects=True)
        except requests.RequestException as e:
            last = str(e)
            time.sleep(1 + i)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            last, last_resp = f"HTTP {r.status_code}", (r.status_code, _err_body(r))
            if i < retries:
                time.sleep(2 * (i + 1))
            continue
        if text:
            val = {"status": r.status_code, "url": r.url, "text": r.text[:200000]}
        else:
            if r.status_code >= 400:
                raise HttpError(r.status_code, url, _err_body(r))
            val = r.json()
        if ttl and (text or r.status_code < 400):
            _db().execute("insert or replace into kv values (?,?,?)", (key, json.dumps(val), time.time()))
            _db().commit()
        return val
    if last_resp:
        raise HttpError(last_resp[0], url, last_resp[1])
    raise RuntimeError(f"{method} {url} failed: {last}")


def final_url(url, timeout=10):
    """Follow redirects (e.g. Product Hunt tracking links) and return the landing URL, or None."""
    try:
        r = requests.get(url, allow_redirects=True, timeout=timeout, stream=True, headers={"User-Agent": UA})
        u = r.url
        r.close()
        return u
    except requests.RequestException:
        return None
