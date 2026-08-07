"""Build the cash_ledger from the broker exports, so the club's cash balance
is derivable without the xlsx meeting sheets.

Sources:
- Bolero xlsx: Cash rows (dividends, provisioning) AND security trades
  (buy = cash out, sell = cash in).
- Binck xlsx: 'Saldo mutatie' per trade (signed cash effect).
- One synthetic 'seed' row anchoring the Bolero-era balance to the known
  38,810.98 EUR cash on the 24-10-2025 meeting sheet.

Idempotent: upserts on (source, txn_date, kind, amount_eur, description).
Usage: .venv/bin/python ingest_cash.py [--dry-run]
"""
import re
import sys
from datetime import datetime

import openpyxl

from common import ROOT, Supa
from ingest_transactions import bolero_date, parse_all

DOCS = ROOT / "Documenten"
BOLERO_START = "2025-07-01"
ANCHOR_DATE, ANCHOR_CASH = "2025-10-24", 38810.98  # cash on the 24-10-2025 sheet


def bolero_cash_rows():
    ws = openpyxl.load_workbook(DOCS / "Transacties Bolero op 7 aug 2026.xlsx",
                                data_only=True).active
    out = []
    for row in list(ws.iter_rows(values_only=True))[1:]:
        d, _ttype, kind, details, value, _ = row
        if kind != "Cash" or not details:
            continue
        amount = float(str(value).replace(".", "").replace(",", ".").replace("+", ""))
        desc = str(details).strip()
        if re.match(r"^(Aankoop|Verkoop) Online", desc):
            continue  # cash settlement of a trade — already counted via transactions
        low = desc.lower()
        k = ("dividend" if "dividend" in low else
             "deposit" if "provisionering" in low or "storting" in low else
             "withdrawal" if "opvraging" in low or "uitbetaling rekening" in low else
             "fee" if "kost" in low or "taks" in low or "belasting" in low else
             "other")
        out.append({"txn_date": bolero_date(d), "kind": k, "amount_eur": round(amount, 2),
                    "description": desc[:120], "source": "bolero"})
    return out


def trade_cash_rows(txns):
    out = []
    for t in txns:
        sign = -1 if t["side"] == "buy" else 1
        out.append({"txn_date": t["txn_date"],
                    "kind": "trade_buy" if t["side"] == "buy" else "trade_sell",
                    "amount_eur": round(sign * t["amount_eur"], 2),
                    "description": f"{t['side']} {t['holding_name']}"[:120],
                    "source": t["source"]})
    return out


def main():
    dry = "--dry-run" in sys.argv
    txns = parse_all()
    rows = bolero_cash_rows() + trade_cash_rows(txns)

    # seed so that the Bolero-era cumulative equals the known anchor balance
    bolero_rows = [r for r in rows if r["txn_date"] >= BOLERO_START]
    upto_anchor = sum(r["amount_eur"] for r in bolero_rows if r["txn_date"] <= ANCHOR_DATE)
    seed = round(ANCHOR_CASH - upto_anchor, 2)
    rows.append({"txn_date": BOLERO_START, "kind": "seed", "amount_eur": seed,
                 "description": f"startsaldo Bolero-rekening (anker: €{ANCHOR_CASH} op {ANCHOR_DATE})",
                 "source": "seed"})

    rows.sort(key=lambda r: r["txn_date"])
    print(f"{len(rows)} ledger rows (seed €{seed})")
    bal = 0.0
    for r in rows:
        if r["txn_date"] >= BOLERO_START:
            bal += r["amount_eur"]
            if r["txn_date"] in ("2026-02-06", "2026-08-06") or dry:
                print(f"  {r['txn_date']} {r['kind']:10} {r['amount_eur']:+10.2f} -> saldo {bal:10.2f}  {r['description'][:50]}")
    print(f"saldo einde ledger: €{bal:.2f}")
    if dry:
        return
    Supa().upsert("cash_ledger", rows, on_conflict="source,txn_date,kind,amount_eur,description")
    print("Upserted into Supabase.")


if __name__ == "__main__":
    main()
