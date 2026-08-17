"""Export everything the GitHub Pages dashboard needs to data/dashboard.json.

Pulls holdings/snapshots/totals/news/digests from Supabase, fetches live prices
via yfinance for active AND sold positions, and computes the FOMO list (sold
positions that kept rising = missed gains) and the DAB list ("Dodged A Bullet":
sold positions that fell = losses avoided).

Run after each ingest / digest:  .venv/bin/python export_dashboard.py
Then commit data/dashboard.json to the dashboard repo.
"""
import json
from datetime import date
from pathlib import Path

import yfinance as yf

from common import ROOT, Supa


def load_txns(s, snapshots):
    """Transactions from Supabase; falls back to parsing the local broker
    xlsx files (which don't exist in CI) when the table is empty/missing."""
    try:
        rows = s.select("transactions", {"select": "txn_date,side,holding_name,shares,amount_eur,price_eur,source",
                                         "order": "txn_date.asc", "limit": "10000"})
        rows = [{**r, "shares": float(r["shares"]) if r["shares"] is not None else None,
                 "price_eur": float(r["price_eur"]) if r["price_eur"] is not None else None} for r in rows]
        if rows:
            return rows
    except Exception:
        pass
    from ingest_transactions import parse_all
    return parse_all(snapshots)

OUT = ROOT / "data" / "dashboard.json"
DELISTED = {"ABLX.BR": "overgenomen door Sanofi (2018)",
            "ZTS.BR": "overgenomen door Panasonic (2017)",
            "HBM.DE": "van de beurs gehaald (2022)"}
# Bought out at a fixed price — that price IS the missed/avoided return.
FINAL_PRICES = {"WHATS.BR": (148.0, "EUR", "uitgekocht aan €148/aandeel (mei 2026)")}


def ticker_currency(ticker):
    if ticker.endswith(".SW"):
        return "CHF"
    if "." in ticker or ticker.endswith((".AS", ".BR", ".DE", ".L")):
        return "EUR" if not ticker.endswith(".L") else "GBP"
    return "USD"


def live_prices(tickers):
    """Last close per ticker; silently skips symbols yfinance can't resolve."""
    prices = {}
    for t in tickers:
        try:
            h = yf.Ticker(t).history(period="5d")["Close"].dropna()
            if len(h):
                px = float(h.iloc[-1])
                if t.endswith(".L"):
                    px /= 100  # LSE quotes in pence
                prices[t] = round(px, 4)
        except Exception:
            pass
    return prices


_SPLITS = {}


def split_factor(ticker, since_date):
    """Cumulative share-split factor after since_date (1.0 if none)."""
    if ticker not in _SPLITS:
        try:
            _SPLITS[ticker] = [(str(d.date()), float(r)) for d, r in yf.Ticker(ticker).splits.items()]
        except Exception:
            _SPLITS[ticker] = []
    f = 1.0
    for d, ratio in _SPLITS[ticker]:
        if d > since_date and ratio:
            f *= ratio
    return f


def select_all(s, table, params):
    """Paginate past PostgREST's max-rows cap."""
    rows, off, page = [], 0, 1000
    while True:
        batch = s.select(table, {**params, "limit": str(page), "offset": str(off)})
        rows.extend(batch)
        if len(batch) < page:
            return rows
        off += page


# The club moved Binck -> (Saxo) -> Bolero; the whole portfolio was liquidated
# around the 2023-05-06 meeting and rebuilt from 2025-07-16 (first Bolero buy).
LIQUIDATION = "2023-05-13"
FIRST_POST_GAP_MEETING = "2025-10-24"


def build_timeline(snapshots, totals, txns):
    """(date, {holding: (shares, ref_date)}) position points over time.
    Meeting snapshots are the authoritative anchors (positions reset to the
    sheet); broker transactions adjust positions *between* meetings so buys/
    sells take effect on their real date. The 2023 liquidation empties the
    portfolio until the Bolero rebuild."""
    by_meeting = {}
    for sn in snapshots:
        by_meeting.setdefault(sn["meeting_date"], {})[sn["holding_name"]] = sn
    first_meeting = min(by_meeting)
    events = [(m, "meeting", snaps) for m, snaps in by_meeting.items()]
    events += [(LIQUIDATION, "liquidation", None)]
    events += [(t["txn_date"], "txn", t) for t in txns
               if t["shares"] and t["txn_date"] > first_meeting]
    events.sort(key=lambda e: (e[0], e[1] != "meeting"))  # meeting wins on same date

    points, pos = [], {}
    for d, kind, payload in events:
        if kind == "meeting":
            pos = {n: (sn["shares"] or 0, d) for n, sn in payload.items()}
        elif kind == "liquidation":
            pos = {}
        else:
            shares, ref = pos.get(payload["holding_name"], (0, d))
            shares += payload["shares"] * (1 if payload["side"] == "buy" else -1)
            pos = {**pos, payload["holding_name"]: (shares, ref)}
            if shares <= 0:
                pos.pop(payload["holding_name"])
        points.append((d, pos))
    return points


def weekly_series(s, holdings, snapshots, totals, txns):
    """Continuous weekly securities value in EUR: for each week, the shares
    held at the most recent meeting x that week's avg price (split-corrected,
    FX-converted). Falls back to the meeting valuation for tickers without
    price history (delisted/broken)."""
    prices = select_all(s, "prices_weekly", {"select": "ticker,week_start,avg_price,currency",
                                             "order": "ticker.asc,week_start.asc"})
    if not prices:
        return []
    px = {}
    for p in prices:
        px.setdefault(p["ticker"], {})[p["week_start"]] = (float(p["avg_price"]), p["currency"])
    fx_hist = {"USD": px.pop("EURUSD=X", {}), "CHF": px.pop("EURCHF=X", {})}

    from datetime import date, timedelta
    tick = {h["name"]: h["ticker"] for h in holdings}
    meetings = sorted({t["meeting_date"] for t in totals})
    cash_at = {t["meeting_date"]: t.get("cash_eur") for t in totals}
    snap_at = {}
    for sn in snapshots:
        snap_at[(sn["meeting_date"], sn["holding_name"])] = sn
    timeline = build_timeline(snapshots, totals, txns)

    first = date.fromisoformat(meetings[0])
    monday = first - timedelta(days=first.weekday())
    weeks = []
    while monday <= date.today():
        weeks.append(monday.isoformat())
        monday += timedelta(days=7)

    def week_val(series, wk):
        """Value at week wk, carrying the last known week forward."""
        if not series:
            return None
        keys = [k for k in series if k <= wk]
        return series[max(keys)] if keys else None

    def monday_of(d):
        dd = date.fromisoformat(d)
        return (dd - timedelta(days=dd.weekday())).isoformat()

    out, ti = [], 0
    for wk in weeks:
        # a point takes effect in the week that contains it, so the meeting
        # week is valued with the meeting's own portfolio
        while ti + 1 < len(timeline) and monday_of(timeline[ti + 1][0]) <= wk:
            ti += 1
        tdate, positions = timeline[ti]
        total = 0.0
        for name, (shares, ref) in positions.items():
            t = tick.get(name)
            hit = week_val(px.get(t, {}), wk) if t else None
            if hit:
                price, ccy = hit
                rate = 1.0
                if ccy in fx_hist:
                    r = week_val(fx_hist[ccy], wk)
                    rate = 1.0 / r[0] if r else 1.0
                total += price * shares * split_factor(t, ref) * rate
            else:
                sn = snap_at.get((ref, name))
                if sn and sn.get("value_eur"):
                    total += sn["value_eur"]  # no history: hold the meeting valuation
        mdate = max((m for m in meetings if m <= wk), default=meetings[0])
        meeting_here = next((m for m in meetings if wk <= m < (date.fromisoformat(wk) + timedelta(days=7)).isoformat()), None)
        out.append({"week": wk, "securities_eur": round(total, 2),
                    "cash_eur": cash_at.get(mdate), "meeting": meeting_here})

    # sanity: compare computed value vs sheet value at meeting weeks
    devs = []
    for o in out:
        if o["meeting"]:
            sheet = next((t.get("securities_value_eur") for t in totals if t["meeting_date"] == o["meeting"]), None)
            if sheet:
                devs.append(abs(o["securities_eur"] / sheet - 1))
    if devs:
        print(f"  weekly-series check: mean deviation vs sheet at meetings = {100*sum(devs)/len(devs):.1f}% ({len(devs)} meetings)")
    return out


# Sector per individual stock (ETFs/trackers are shown as one asset class,
# not by sector). First draft — adjust labels as the club prefers.
SECTOR_MAP = {
    "AGEAS NV/SA": "Finance & insurance",
    "FLOW TRADERS LTD": "Finance & insurance",
    "BERKSHIRE HATHAWAY INC. -B-": "Holdings",
    "BREDERODE": "Holdings",
    "SOFINA": "Holdings",
    "MONTEA NV GVV": "Real estate",
    "NOVO-NORDISK A/S  ADR RKS B": "Healthcare",
    "MERCADOLIBRE INC": "Tech",
    "BARRICK MINING CORPORATION": "Commodities",
    "ARCADIS NV": "Industry & Engineering",
}

# Geographic split per holding (fractions per continent). Stocks follow the
# company's home market; ETF splits are approximations of the fund factsheets.
GEO_MAP = {
    "AGEAS NV/SA": {"Europa": 1.0},
    "ARCADIS NV": {"Europa": 1.0},
    "BREDERODE": {"Europa": 1.0},
    "FLOW TRADERS LTD": {"Europa": 1.0},
    "MONTEA NV GVV": {"Europa": 1.0},
    "SOFINA": {"Europa": 1.0},
    "NOVO-NORDISK A/S  ADR RKS B": {"Europa": 1.0},
    "BERKSHIRE HATHAWAY INC. -B-": {"Noord-Amerika": 1.0},
    "BARRICK MINING CORPORATION": {"Noord-Amerika": 1.0},
    "MERCADOLIBRE INC": {"Latijns-Amerika": 1.0},
    "ISHAR.III PLC CORE MSCI WORLD KAP": {"Noord-Amerika": 0.72, "Europa": 0.17, "Azië-Pacific": 0.10, "Afrika & Midden-Oosten": 0.01},
    "ISHARES PLC CORE MSC E.M.IM UC ET K": {"Azië-Pacific": 0.78, "Latijns-Amerika": 0.08, "Europa": 0.04, "Afrika & Midden-Oosten": 0.10},
    "ISHARES II PLC S&P GLOB. WATER FD D": {"Noord-Amerika": 0.55, "Europa": 0.35, "Azië-Pacific": 0.05, "Afrika & Midden-Oosten": 0.05},
    "XTRACKER SILVER ETC EUR ETC": {"Wereldwijd (grondstof)": 1.0},
}

BASELINE_WEEK = "2025-07-14"  # sheet: "Rendementen sinds 16/07/2025" (Bolero restart)
BOLERO_START = "2025-07-01"   # cash ledger is only anchored from the Bolero era on
# USD-quoted benchmarks are converted to EUR, like the sheet does
BENCH_TICKERS = {"^GSPC": ("sp500", "USD"), "URTH": ("msci_world", "USD"),
                 "^STOXX50E": ("eurostoxx50", None)}


def load_cash_ledger(s):
    """Bolero-era cash ledger rows from Supabase, or rebuilt from the local
    broker files (absent in CI) as fallback. Returns [] when neither exists.
    Binck-era rows are excluded: without that era's deposits the running
    balance would be meaningless."""
    rows = []
    try:
        rows = [{**r, "amount_eur": float(r["amount_eur"])}
                for r in s.select("cash_ledger", {"select": "txn_date,kind,amount_eur",
                                                  "order": "txn_date.asc", "limit": "10000"})]
    except Exception:
        pass
    if not rows:
        try:
            import ingest_cash
            rows = sorted(ingest_cash.bolero_cash_rows() +
                          ingest_cash.trade_cash_rows(ingest_cash.parse_all()),
                          key=lambda r: r["txn_date"])
        except Exception:
            return []
    return [r for r in rows if r["txn_date"] >= BOLERO_START]


def benchmark_series(s, weekly, ledger):
    """Weekly indexed returns since BASELINE_WEEK for the benchmarks, plus a
    flow-adjusted (TWR) portfolio return over securities+cash."""
    rows = select_all(s, "prices_weekly", {"select": "ticker,week_start,avg_price",
                                           "currency": "in.(IDX,FX)",
                                           "order": "ticker.asc,week_start.asc"})
    if not rows:
        return []
    px = {}
    for r in rows:
        px.setdefault(r["ticker"], {})[r["week_start"]] = float(r["avg_price"])

    def idx_eur(t, ccy, wk):
        """Benchmark level converted to EUR when USD-quoted (like the sheet)."""
        v = px.get(t, {}).get(wk)
        if v is None:
            return None
        if ccy == "USD":
            r = px.get("EURUSD=X", {}).get(wk)
            return v / r if r else None
        return v

    from datetime import date, timedelta
    flows, cum_cash = {}, {}
    bal = 0.0
    for r in ledger:
        d = date.fromisoformat(r["txn_date"])
        wk = (d - timedelta(days=d.weekday())).isoformat()
        bal += r["amount_eur"]
        cum_cash[wk] = bal
        if r["kind"] in ("deposit", "withdrawal", "seed"):
            flows[wk] = flows.get(wk, 0.0) + r["amount_eur"]

    out, prev_v, chain, last_cash = [], None, 1.0, 0.0
    for w in weekly:
        wk = w["week"]
        if wk < BASELINE_WEEK:
            continue
        last_cash = cum_cash.get(wk, last_cash)
        v = w["securities_eur"] + last_cash
        if prev_v and prev_v > 0:
            chain *= (v - flows.get(wk, 0.0)) / prev_v
        prev_v = v
        point = {"week": wk, "portfolio": round(chain - 1, 4) if ledger else None,
                 "total_eur": round(v, 2)}
        for t, (key, ccy) in BENCH_TICKERS.items():
            base, cur = idx_eur(t, ccy, BASELINE_WEEK), idx_eur(t, ccy, wk)
            point[key] = round(cur / base - 1, 4) if base and cur else None
        out.append(point)
    return out


def split_digest(row):
    """digests.markdown_content may carry a short WhatsApp version after a
    ---WHATSAPP--- delimiter; split it into its own field for the dashboard."""
    md = row.get("markdown_content") or ""
    if "---WHATSAPP---" in md:
        full, wa = md.split("---WHATSAPP---", 1)
        return {**row, "markdown_content": full.strip(), "whatsapp": wa.strip()}
    return {**row, "whatsapp": None}


def latest_digest_row(db_rows):
    """Prefer the digests table, but fall back to the newest digests/YYYY-MM-DD.md
    file when it's newer — the cloud digest routine can't reach Supabase (egress
    proxy blocks the host) and only commits the file."""
    import glob, os, re
    db = db_rows[0] if db_rows else None
    files = sorted(f for f in glob.glob(os.path.join(os.path.dirname(__file__), "digests", "*.md"))
                   if re.match(r"\d{4}-\d{2}-\d{2}\.md$", os.path.basename(f)))
    if not files:
        return db
    fdate = os.path.basename(files[-1])[:-3]
    if db and (db.get("generated_at") or "")[:10] >= fdate:
        return db
    with open(files[-1], encoding="utf-8") as fh:
        return {"generated_at": fdate, "period_start": None, "period_end": fdate,
                "markdown_content": fh.read()}


def fx_to_eur():
    rates = {"EUR": 1.0}
    for pair, ccy in (("EURUSD=X", "USD"), ("EURCHF=X", "CHF"), ("EURGBP=X", "GBP")):
        try:
            h = yf.Ticker(pair).history(period="5d")["Close"].dropna()
            rates[ccy] = 1.0 / float(h.iloc[-1])
        except Exception:
            pass
    return rates


def main():
    s = Supa()
    holdings = s.select("holdings", {"select": "name,ticker,currency,active", "order": "name.asc"})
    snapshots = s.select("snapshots", {"select": "*", "order": "meeting_date.asc,value_eur.desc", "limit": "10000"})
    totals = s.select("portfolio_totals", {"select": "*", "order": "meeting_date.asc"})
    news = s.select("news_items", {"select": "holding_name,headline,url,source,published_at,summary,sentiment",
                                   "order": "published_at.desc", "limit": "200"})
    digests = s.select("digests", {"select": "generated_at,period_start,period_end,markdown_content",
                                   "order": "generated_at.desc", "limit": "1"})

    by_name = {h["name"]: h for h in holdings}
    last_snap = {}
    for snap in snapshots:  # snapshots are date-ascending, so this keeps the latest
        last_snap[snap["holding_name"]] = snap

    tickers = [h["ticker"] for h in holdings
               if h["ticker"] and h["ticker"] not in DELISTED and h["ticker"] not in FINAL_PRICES]
    prices = live_prices(tickers)
    fx = fx_to_eur()
    if "ROG.SW" in tickers and "ROG.SW" not in prices:
        # Yahoo's ROG.SW quote is broken; derive CHF price from the RHHBY ADR (1/8 share, USD)
        adr = live_prices(["RHHBY"]).get("RHHBY")
        if adr and fx.get("USD") and fx.get("CHF"):
            prices["ROG.SW"] = round(adr * 8 * fx["USD"] / fx["CHF"], 2)

    txns = load_txns(s, snapshots)
    last_sell = {}
    for tx in txns:
        if tx["side"] == "sell" and tx["shares"] and tx["price_eur"]:
            last_sell[tx["holding_name"]] = tx

    from datetime import date as _date, timedelta as _td
    fomo, dab = [], []
    for name, h in by_name.items():
        if h["active"]:
            continue
        exit_snap = last_snap.get(name)
        t = h["ticker"]
        # Prefer the real sell transaction as exit if it (roughly) closed the
        # position: dated no more than ~6 months before the holding's last
        # meeting appearance. Older sells are partial (e.g. Umicore 2017).
        sell = last_sell.get(name)
        use_txn = sell and sell["txn_date"] >= (_date.fromisoformat(exit_snap["meeting_date"]) - _td(days=180)).isoformat()
        entry = {"name": name, "ticker": t,
                 "exit_date": sell["txn_date"] if use_txn else exit_snap["meeting_date"],
                 "exit_source": "transactie" if use_txn else "laatste vergadering"}
        if t in DELISTED:
            entry["note"] = DELISTED[t]
            entry["change_pct"] = None
            fomo.append(entry)  # shown greyed-out in a separate footnote row
            continue
        if t in FINAL_PRICES:
            px, ccy, note = FINAL_PRICES[t]
            entry["note"] = note
        else:
            px, ccy = prices.get(t), ticker_currency(t)
        if px is None:
            continue
        # Broker/sheet prices are as-traded; Yahoo quotes are split-adjusted (Tesla 15x)
        factor = split_factor(t, entry["exit_date"])
        if use_txn:  # sell proceeds are in EUR -> compare in EUR
            exit_px = sell["price_eur"] / factor
            shares = sell["shares"] * factor
            cur = px * fx.get(ccy, 1.0)
            ccy = "EUR"
        else:
            if not exit_snap["price"]:
                continue
            exit_px = exit_snap["price"] / factor
            shares = (exit_snap["shares"] or 0) * factor
            cur = px
        change = cur / exit_px - 1
        missed_eur = (cur - exit_px) * shares * fx.get(ccy, 1.0)
        entry.update(exit_price=round(exit_px, 4), shares=shares, split_factor=factor,
                     current_price=px, currency=ccy, change_pct=round(change, 4),
                     impact_eur=round(missed_eur, 2))
        (fomo if change > 0 else dab).append(entry)

    fomo = ([e for e in fomo if e["change_pct"] is not None] +
            [e for e in fomo if e["change_pct"] is None])
    fomo.sort(key=lambda e: -(e.get("impact_eur") or 0))
    dab.sort(key=lambda e: e.get("impact_eur") or 0)

    live_active = {h["ticker"]: prices.get(h["ticker"]) for h in holdings if h["active"] and h["ticker"]}

    data = {
        "generated_at": date.today().isoformat(),
        "fx_eur": fx,
        "holdings": holdings,
        "snapshots": snapshots,
        "portfolio_totals": totals,
        "news": news,
        "latest_digest": (lambda r: split_digest(r) if r else None)(latest_digest_row(digests)),
        "live_prices_active": live_active,
        "weekly_value": (weekly := weekly_series(s, holdings, snapshots, totals, txns)),
        "benchmark_series": benchmark_series(s, weekly, load_cash_ledger(s)),
        "fomo": fomo,
        "dab": dab,
        "sectors": SECTOR_MAP,
        "geo": GEO_MAP,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False))
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB): "
          f"{len(snapshots)} snapshots, {len(totals)} meetings, "
          f"{len(fomo)} FOMO, {len(dab)} DAB, {len(prices)} live prices")


if __name__ == "__main__":
    main()
