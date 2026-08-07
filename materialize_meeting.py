"""Materialize a meeting snapshot WITHOUT the xlsx sheet: positions come from
transactions, prices from prices_weekly, cash from cash_ledger, benchmarks
from the index tickers. Writes the same `snapshots` + `portfolio_totals` rows
the sheet ingest used to produce — the meeting sheet becomes output, not input.

Usage:
    python materialize_meeting.py --date 2026-08-06 --dry-run   # compare only
    python materialize_meeting.py --date 2026-10-02             # write
"""
import argparse
from datetime import date, timedelta

from common import Supa
from export_dashboard import (BASELINE_WEEK, BENCH_TICKERS, benchmark_series,
                              build_timeline, load_cash_ledger, load_txns,
                              select_all, split_factor, weekly_series)


def monday(d):
    dd = date.fromisoformat(d)
    return (dd - timedelta(days=dd.weekday())).isoformat()


def avg_cost(txns, name, upto):
    """Average-cost basis of the open position in `name` on date `upto`.
    Starts counting after the 2023 liquidation: the Saxo-era sales are not in
    the transaction files, so older buys would pollute the basis."""
    from export_dashboard import LIQUIDATION
    shares = cost = 0.0
    for t in txns:
        if (t["holding_name"] != name or not t["shares"]
                or t["txn_date"] <= LIQUIDATION or t["txn_date"] > upto):
            continue
        if t["side"] == "buy":
            shares += t["shares"]
            cost += t["amount_eur"]
        elif shares > 0:
            frac = min(t["shares"] / shares, 1.0)
            cost *= (1 - frac)
            shares -= t["shares"]
    return (round(cost / shares, 4), round(cost, 2)) if shares > 0 else (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    D, wk = args.date, monday(args.date)

    s = Supa()
    holdings = s.select("holdings", {"select": "name,ticker,currency,active"})
    snapshots = s.select("snapshots", {"select": "*", "order": "meeting_date.asc", "limit": "10000"})
    totals = s.select("portfolio_totals", {"select": "*", "order": "meeting_date.asc"})
    txns = load_txns(s, snapshots)
    ledger = load_cash_ledger(s)
    tick = {h["name"]: h["ticker"] for h in holdings}

    prices = select_all(s, "prices_weekly", {"select": "ticker,week_start,avg_price,currency",
                                             "order": "ticker.asc,week_start.asc"})
    px = {}
    for p in prices:
        px.setdefault(p["ticker"], {})[p["week_start"]] = (float(p["avg_price"]), p["currency"])
    fx = {"USD": px.get("EURUSD=X", {}), "CHF": px.get("EURCHF=X", {})}

    def price_at(t, w):
        series = px.get(t, {})
        keys = [k for k in series if k <= w]
        return series[max(keys)] if keys else None

    # positions on D from the transaction/meeting timeline (excluding D itself
    # if a sheet-derived snapshot for D already exists, we rebuild from scratch)
    timeline = build_timeline([sn for sn in snapshots if sn["meeting_date"] < D], totals, txns)
    pos = {}
    for d0, p in timeline:
        if d0 <= D:
            pos = p

    prev_meeting = max((t["meeting_date"] for t in totals if t["meeting_date"] < D), default=None)
    prev_snap = {sn["holding_name"]: sn for sn in snapshots if sn["meeting_date"] == prev_meeting}

    rows, sec_total, eur_val, usd_val = [], 0.0, 0.0, 0.0
    for name, (shares, ref) in sorted(pos.items()):
        t = tick.get(name)
        hit = price_at(t, wk) if t else None
        if not hit or shares <= 0:
            continue
        price, ccy = hit
        rate = 1.0
        if ccy in fx:
            r = price_at(ccy and {"USD": "EURUSD=X", "CHF": "EURCHF=X"}[ccy], wk)
            rate = 1.0 / r[0] if r else 1.0
        factor = split_factor(t, ref)
        eff_shares = shares * factor
        value = price * eff_shares * rate
        sec_total += value
        if ccy == "USD":
            usd_val += value
        else:
            eur_val += value
        pprice, pvalue = avg_cost(txns, name, D)
        prev = prev_snap.get(name)
        rows.append({"meeting_date": D, "holding_name": name, "currency": ccy if ccy != "IDX" else "EUR",
                     "shares": eff_shares, "price": round(price, 4),
                     "prev_price": prev["price"] if prev else None,
                     "value_eur": round(value, 2), "weight": None,
                     "return_since_prev": round(price / prev["price"] - 1, 6) if prev and prev["price"] else None,
                     "purchase_price": pprice, "purchase_value_eur": pvalue,
                     "unrealized_pnl_eur": round(value - pvalue, 2) if pvalue else None,
                     "unrealized_pnl_pct": round(value / pvalue - 1, 6) if pvalue else None})
    for r in rows:
        r["weight"] = round(r["value_eur"] / sec_total, 6) if sec_total else None

    cash = round(sum(r["amount_eur"] for r in ledger if r["txn_date"] <= D), 2) if ledger else None  # ledger is Bolero-era only
    weekly = weekly_series(s, holdings, snapshots, totals, txns)
    bench = benchmark_series(s, weekly, ledger)
    bpoint = next((b for b in reversed(bench) if b["week"] <= wk), {})

    total_row = {"meeting_date": D, "securities_value_eur": round(sec_total, 2),
                 "cash_eur": cash,
                 "total_value_eur": round(sec_total + (cash or 0), 2),
                 "eur_exposure": round((eur_val + (cash or 0)) / (sec_total + (cash or 0)), 6) if sec_total else None,
                 "usd_exposure": round(usd_val / (sec_total + (cash or 0)), 6) if sec_total else None,
                 "return_portfolio": bpoint.get("portfolio"),
                 "return_sp500": bpoint.get("sp500"),
                 "return_msci_world": bpoint.get("msci_world"),
                 "return_eurostoxx50": bpoint.get("eurostoxx50")}

    print(f"Vergadering {D}: {len(rows)} posities, effecten €{sec_total:,.2f}, cash €{cash}, "
          f"totaal €{total_row['total_value_eur']:,.2f}")
    for r in rows:
        print(f"  {r['holding_name'][:34]:36} {r['shares']:>8} x {r['price']:<9} = €{r['value_eur']:>10,.2f}"
              f"  ({(r['weight'] or 0)*100:4.1f}%)  Δaankoop {r['unrealized_pnl_pct']}")
    print("benchmarks:", {k: bpoint.get(k) for k in ("portfolio", "sp500", "msci_world", "eurostoxx50")})

    existing = next((t for t in totals if t["meeting_date"] == D), None)
    if existing:
        print(f"\nNB: blad-gebaseerde rij voor {D} bestaat al — vergelijk: "
              f"effecten €{existing.get('securities_value_eur')}, cash €{existing.get('cash_eur')}")
    if args.dry_run:
        return
    s.upsert("snapshots", rows, on_conflict="meeting_date,holding_name")
    s.upsert("portfolio_totals", [total_row], on_conflict="meeting_date")
    print("Weggeschreven naar Supabase.")


if __name__ == "__main__":
    main()
