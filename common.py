"""Shared helpers: .env loading + minimal Supabase REST client (PostgREST)."""
import os
from pathlib import Path

import requests

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
        r = requests.get(f"{self.base}/{table}", params=params or {}, headers=self.h, timeout=30)
        r.raise_for_status()
        return r.json()

    def upsert(self, table, rows, on_conflict):
        """Insert rows, merging duplicates on the given conflict columns."""
        r = requests.post(
            f"{self.base}/{table}",
            params={"on_conflict": on_conflict},
            json=rows,
            headers={**self.h, "Prefer": "resolution=merge-duplicates,return=minimal"},
            timeout=60)
        if not r.ok:
            raise RuntimeError(f"{table} upsert failed ({r.status_code}): {r.text[:300]}")

    def insert(self, table, rows):
        r = requests.post(f"{self.base}/{table}", json=rows,
                          headers={**self.h, "Prefer": "return=representation"}, timeout=60)
        r.raise_for_status()
        return r.json()
