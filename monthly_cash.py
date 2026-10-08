"""Maandelijkse cashboekingen in cash_ledger: op de 1e van elke maand stort elk
lid zijn bijdrage, en Bolero rekent een vaste maandkost aan.

Draait idempotent (upsert op source,txn_date,kind,amount_eur,description), lokaal
of in de GitHub Action vóór export_dashboard.py. Boekt alleen maanden vanaf START
tot en met vandaag. Als voor een maand al een échte Bolero-storting (source
'bolero', kind 'deposit') in de ledger staat, wordt de geplande storting van die
maand weer verwijderd zodat niets dubbel telt.

Pas MEMBERS / PER_MEMBER / FEE aan als de club verandert.
"""
from datetime import date

from common import Supa

MEMBERS = 11
PER_MEMBER = 50.00
FEE = 2.50
START = "2026-11-01"   # eerste automatisch geboekte maand (okt 2026 is handmatig afgestemd op 8 okt)
SOURCE = "schedule"


def first_of_months(start, end):
    y, m = int(start[:4]), int(start[5:7])
    while True:
        d = date(y, m, 1)
        if d > end:
            return
        yield d.isoformat()
        m += 1
        if m > 12:
            y, m = y + 1, 1


def main():
    s = Supa()
    today = date.today()
    deposit_desc = f"Maandelijkse storting: {MEMBERS} leden x EUR {PER_MEMBER:.2f}"
    fee_desc = "Maandelijkse rekeningkost Bolero"
    rows = []
    for d in first_of_months(START, today):
        rows.append({"txn_date": d, "kind": "deposit", "amount_eur": round(MEMBERS * PER_MEMBER, 2),
                     "description": deposit_desc, "source": SOURCE})
        rows.append({"txn_date": d, "kind": "fee", "amount_eur": -FEE,
                     "description": fee_desc, "source": SOURCE})
    if not rows:
        print(f"Nog geen maand te boeken (START={START}, vandaag {today}).")
        return
    s.upsert("cash_ledger", rows, on_conflict="source,txn_date,kind,amount_eur,description")
    print(f"{len(rows)//2} maand(en) geboekt/bevestigd t/m {rows[-1]['txn_date']}: "
          f"+{MEMBERS*PER_MEMBER:.2f} storting en -{FEE:.2f} kost per maand.")

    # dubbeltelling vermijden: echte Bolero-storting in die maand -> geplande storting weg
    bolero = s.select("cash_ledger", {"select": "txn_date", "source": "eq.bolero", "kind": "eq.deposit",
                                      "txn_date": f"gte.{START}", "limit": "1000"})
    months_real = {r["txn_date"][:7] for r in bolero}
    for d in first_of_months(START, today):
        if d[:7] in months_real:
            s.delete("cash_ledger", {"source": f"eq.{SOURCE}", "kind": "eq.deposit", "txn_date": f"eq.{d}"})
            print(f"  {d[:7]}: echte Bolero-storting aanwezig, geplande storting verwijderd.")

    bal = sum(float(r["amount_eur"]) for r in
              s.select("cash_ledger", {"select": "amount_eur", "txn_date": "gte.2025-07-01", "limit": "10000"}))
    print(f"Cash volgens ledger vandaag: EUR {bal:,.2f}")


if __name__ == "__main__":
    main()
