"""Backfill/refresh weekly price history (avg of week open & close) into
Supabase prices_weekly, for every holding ticker plus the FX pairs needed to
convert USD/CHF positions to EUR. Idempotent (upsert on ticker+week_start);
re-running only adds new weeks.

Usage:  .venv/bin/python backfill_prices.py
"""
import yfinance as yf

from common import Supa

FX_PAIRS = {"EURUSD=X": "FX", "EURCHF=X": "FX"}
BROKEN = {"ROG.SW"}  # Yahoo quote broken; Roche weeks stay empty -> fallback in export


def ticker_currency(t):
    if t.endswith(".SW"):
        return "CHF"
    if t == "B" or "." not in t:
        return "USD"
    return "EUR"


def weekly_rows(ticker, start):
    df = yf.download(ticker, start=start, interval="1wk", progress=False, auto_adjust=True)
    if df is None or df.empty:
        return []
    if hasattr(df.columns, "levels"):  # yfinance MultiIndex columns
        df.columns = df.columns.get_level_values(0)
    ccy = "FX" if ticker in FX_PAIRS else ticker_currency(ticker)
    rows = []
    for idx, r in df.iterrows():
        o, c = r.get("Open"), r.get("Close")
        if o and c and o == o and c == c:  # NaN guard
            rows.append({"ticker": ticker, "week_start": str(idx.date()),
                         "avg_price": round((float(o) + float(c)) / 2, 6), "currency": ccy})
    return rows


def main():
    s = Supa()
    holdings = s.select("holdings", {"select": "name,ticker"})
    # start = first meeting the holding appears on (minus a week of margin)
    firsts = {}
    for snap in s.select("snapshots", {"select": "holding_name,meeting_date",
                                       "order": "meeting_date.asc", "limit": "10000"}):
        firsts.setdefault(snap["holding_name"], snap["meeting_date"])

    # transactions can predate the first meeting appearance (e.g. EMIM bought Feb, first on the Aug sheet)
    try:
        for t in s.select("transactions", {"select": "holding_name,txn_date", "order": "txn_date.asc", "limit": "1000"}):
            firsts[t["holding_name"]] = min(firsts.get(t["holding_name"], t["txn_date"]), t["txn_date"])
    except Exception:
        pass

    jobs = {p: "2015-08-01" for p in FX_PAIRS}
    for h in holdings:
        if h["ticker"] and h["ticker"] not in BROKEN:
            jobs[h["ticker"]] = firsts.get(h["name"], "2015-08-01")

    total = 0
    for ticker, start in sorted(jobs.items()):
        rows = weekly_rows(ticker, start)
        if rows:
            s.upsert("prices_weekly", rows, on_conflict="ticker,week_start")
        total += len(rows)
        print(f"  {ticker:12} {len(rows):5} weeks since {start}")
    print(f"Done: {total} rows upserted across {len(jobs)} tickers.")


if __name__ == "__main__":
    main()
