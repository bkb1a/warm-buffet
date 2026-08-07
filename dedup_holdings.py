"""Rename legacy holding names in Supabase to their canonical form (NAME_MAP),
then re-run ingest to restore merged rows. Idempotent."""
import requests

from common import Supa
from ingest_rendement import NAME_MAP


def main():
    s = Supa()
    old = ",".join(f'"{n}"' for n in NAME_MAP)
    for table in ("snapshots", "holdings"):
        col = "holding_name" if table == "snapshots" else "name"
        r = requests.delete(f"{s.base}/{table}",
                            params={col: f"in.({old})"},
                            headers={**s.h, "Prefer": "count=exact"}, timeout=60)
        r.raise_for_status()
        print(f"{table}: removed {r.headers.get('Content-Range', '?')} legacy-name rows")
    print("Now re-run ingest_rendement.py to restore canonical rows.")


if __name__ == "__main__":
    main()
