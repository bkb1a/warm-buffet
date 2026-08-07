# 't Warm Buffet — dashboard

Meeting-prep dashboard for the investment club. Hosted on GitHub Pages
(`index.html` + `data/dashboard.json`, fully static — no keys in the repo).

## Refresh flow (before each meeting)

1. Update `Documenten/t Warm Buffet Rendement.xlsx` with the new meeting sheet.
2. `claude "/portfolio-digest"` — ingests the sheet, gathers news, writes the digest.
3. `.venv/bin/python export_dashboard.py` — rebuilds `data/dashboard.json`
   (Supabase data + live prices + FOMO/DAB).
4. Commit & push `data/dashboard.json` (and `digests/`) — Pages refreshes automatically.

The **▶ Nieuwe digest** button will trigger a GitHub Action (workflow_dispatch)
once this repo lives on the club's GitHub account; until then it shows the
manual steps above.

## Dashboard features

- Stat tiles, portfolio value over time (securities vs cash), holdings table
  with live prices, allocation and Δ-per-holding charts, benchmark comparison.
- **Vergelijk met** selector: compare the latest meeting against any previous one.
- **FOMO** 😱: sold positions that kept rising — the return we missed
  (split-adjusted, in EUR). **DAB** 😅 ("Dodged A Bullet"): sold positions that
  fell — the loss we avoided.
- News per holding + the full latest digest, both from Supabase.
