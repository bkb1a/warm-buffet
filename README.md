# 't Warm Buffet — dashboard

Meeting-prep dashboard for the investment club. Hosted on GitHub Pages
(`index.html` + `data/dashboard.json`, fully static — no keys in the repo).

## Hoe de data leeft (xlsx-vrij sinds aug 2026)

- **Dagelijks + zaterdag**: GitHub Action `refresh.yml` backfillt weekkoersen &
  benchmarks en herbouwt `data/dashboard.json` uit Supabase.
- **Tweewekelijks (za, even weken)**: claude.ai cloud-routine schrijft digest +
  nieuws naar Supabase en mailt de WhatsApp-versie; de zaterdag-run van de
  Action zet hem meteen live.
- **Maandelijkse cash**: `monthly_cash.py` boekt op de 1e van elke maand (vanaf
  nov 2026) de ledenbijdrage (11 × €50) en de rekeningkost (€2,50) in
  `cash_ledger` (source `schedule`); draait in de Action vóór de export. Zodra een
  Bolero-export een echte storting voor die maand bevat, verwijdert het script de
  geplande storting van die maand. Aantal leden/bedragen staan bovenaan het script.
  Het dashboard toont cash "live" = ledger tot vandaag (`cash_live`).
- **Nieuwe transacties**: Bolero-export in `Documenten/` zetten en
  `ingest_transactions.py` + `ingest_cash.py` draaien (idempotent).
- **Nieuwe vergadering**: `materialize_meeting.py --date YYYY-MM-DD` genereert
  de snapshot uit transacties + weekkoersen + cash ledger — het xlsx-blad is
  niet meer nodig (`ingest_rendement.py` blijft enkel voor de historiek).
- **Volgende vergadering plannen**: `data/next_meeting.json` bewerken op GitHub.

## Dashboard features

- Stat tiles, portfolio value over time (securities vs cash), holdings table
  with live prices, allocation and Δ-per-holding charts, benchmark comparison.
- **Vergelijk met** selector: compare the latest meeting against any previous one.
- **FOMO** 😱: sold positions that kept rising — the return we missed
  (split-adjusted, in EUR). **DAB** 😅 ("Dodged A Bullet"): sold positions that
  fell — the loss we avoided.
- News per holding + the full latest digest, both from Supabase.
