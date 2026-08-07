

import requests
from common import Supa

# Yahoo Finance-style symbols (exchange suffix: .BR Brussels, .AS Amsterdam,
# .DE Xetra, .SW Zurich, .L London; none = US).
TICKERS = {
    "AB Inbev": "ABI.BR",
    "Ablynx NV": "ABLX.BR",            # delisted 2018, Sanofi takeover
    "AGEAS NV/SA": "AGS.BR",
    "Alibaba Group Holding Ltd  -ADR-": "BABA",
    "ARCADIS NV": "ARCAD.AS",
    "BARRICK MINING CORPORATION": "B",  # NYSE; formerly GOLD
    "BERKSHIRE HATHAWAY INC. -B-": "BRK-B",
    "BREDERODE": "BREB.BR",
    "Exmar NV.": "EXM.BR",
    "FLOW TRADERS LTD": "FLOW.AS",
    "Henkel AG & Co. KGaA": "HEN3.DE",  # preference shares (most traded line)
    "Hornbach Baumarkt AG": "HBM.DE",   # delisted 2022 after squeeze-out
    "Ion Beam Applications": "IBAB.BR",
    "ISHAR.III PLC CORE MSCI WORLD KAP": "IWDA.AS",
    "ISHARES II PLC S&P GLOB. WATER FD D": "IH2O.MI",
    "ISHARES PLC CORE MSC E.M.IM UC ET K": "EMIM.AS",
    "MERCADOLIBRE INC": "MELI",
    "MONTEA NV GVV": "MONT.BR",
    "NOVO-NORDISK A/S  ADR RKS B": "NVO",
    "Ontex Group NV": "ONTEX.BR",
    "Recticel": "RECT.BR",
    "Roche Holding": "ROG.SW",
    "SOFINA": "SOF.BR",
    "Teladoc Health Inc": "TDOC",
    "Teradata Corporation": "TDC",
    "Tesla Inc": "TSLA",
    "Umicore": "UMI.BR",
    "Vanguard FTSE Emerging Markets ETF": "VFEM.AS",
    "Volkswagen AG": "VOW3.DE",         # preference shares (most traded line)
    "What's Cooking (Ter Beke)": "WHATS.BR",
    "XTRACKER SILVER ETC EUR ETC": "XAD6.DE",
    "Zetes Industries SA": "ZTS.BR",    # delisted 2017, Panasonic takeover
}

s = Supa()
names = {h["name"] for h in s.select("holdings", {"select": "name"})}
missing = names - set(TICKERS)
if missing:
    print("No ticker mapped for:", missing)
for name, ticker in TICKERS.items():
    if name not in names:
        print("Not in DB (skipped):", name)
        continue
    r = requests.patch(f"{s.base}/holdings", params={"name": f"eq.{name}"},
                       json={"ticker": ticker}, headers=s.h, timeout=30)
    r.raise_for_status()
print("Updated", len(TICKERS & names if isinstance(TICKERS, set) else names & set(TICKERS)), "holdings")
rows = s.select("holdings", {"select": "name,ticker", "ticker": "is.null"})
print("Still without ticker:", rows or "none")
