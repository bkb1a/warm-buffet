"""Shared helpers: .env loading + minimal Supabase REST client (PostgREST)."""
import os
import time
from pathlib import Path

import requests

RETRY_STATUS = {502, 503, 504}


def _request(method, url, attempts=4, **kw):
    """requests.request with retries on connection errors / transient 5xx."""
    for i in range(attempts):
        try:
            r = requests.request(method, url, **kw)
            if r.status_code in RETRY_STATUS and i < attempts - 1:
                raise requests.ConnectionError(f"HTTP {r.status_code}")
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            if i == attempts - 1:
                raise
            wait = 2 ** i
            print(f"  [retry {i+1}/{attempts-1}] {method} {url.split('/rest/v1/')[-1]}: {e} — sleeping {wait}s")
            time.sleep(wait)

ROOT = Path(__file__).parent


def load_env():
    env = dict(os.environ)
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


class Supa:
    def __init__(self):
        env = load_env()
        self.base = env["SUPABASE_URL"].rstrip("/") + "/rest/v1"
        key = env["SUPABASE_SERVICE_ROLE_KEY"]
        self.h = {"apikey": key, "Authorization": f"Bearer {key}",
                  "Content-Type": "application/json"}

    def select(self, table, params=None):
        r = _request("GET", f"{self.base}/{table}", params=params or {}, headers=self.h, timeout=30)
        r.raise_for_status()
        return r.json()

    def upsert(self, table, rows, on_conflict):
        """Insert rows, merging duplicates on the given conflict columns."""
        r = _request(
            "POST", f"{self.base}/{table}",
            params={"on_conflict": on_conflict},
            json=rows,
            headers={**self.h, "Prefer": "resolution=merge-duplicates,return=minimal"},
            timeout=60)
        if not r.ok:
            raise RuntimeError(f"{table} upsert failed ({r.status_code}): {r.text[:300]}")

    def insert(self, table, rows):
        r = _request("POST", f"{self.base}/{table}", json=rows,
                     headers={**self.h, "Prefer": "return=representation"}, timeout=60)
        r.raise_for_status()
        return r.json()
