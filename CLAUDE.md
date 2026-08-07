# warm-buffet — 't Warm Buffet investment club agent

Analyzes the club's portfolio and gathers holding-relevant news between
meetings, producing an on-demand meeting-prep digest via `/portfolio-digest`.

## Data flow

1. Source of truth: `Documenten/t Warm Buffet Rendement.xlsx` — one sheet per
   meeting (`dd-mm-yyyy`), maintained by the club (Bolero broker, EUR).
2. `ingest_rendement.py` parses every meeting sheet (header-driven — layouts
   changed over the years) and upserts into Supabase. Idempotent; re-run after
   every new meeting sheet.
3. `/portfolio-digest` skill (in `~/.claude/skills/portfolio-digest/`) refreshes
   data, WebSearches news per holding since the previous meeting, and writes a
   digest to `digests/YYYY-MM-DD.md` + the `digests` table.

## Database

Supabase project `nkxoqzbkhetdfeaqgmaw` (personal — NOT the GUS Foods org, not
reachable via the Supabase MCP connector). Access via PostgREST REST API using
`.env` (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`); helper client in
`common.py` (`Supa`). Schema in `schema.sql` — apply via the Supabase dashboard
SQL editor (PostgREST can't run DDL).

Tables: `holdings` (distinct positions, active flag), `snapshots` (per holding
per meeting), `portfolio_totals` (per meeting: totals, cash, FX exposure,
benchmark returns), `news_items`, `digests`.

## Commands

```sh
.venv/bin/python ingest_rendement.py --dry-run   # parse only, print summary
.venv/bin/python ingest_rendement.py             # ingest into Supabase
```

## Caveats

- `unrealized_pnl_pct` is a fraction in recent sheets, percent units pre-2016.
- Pre-2020 sheets lack labeled totals rows → `portfolio_totals` sparse there.
- Meeting sheets 2013–2026 also exist as folders in `Documenten/Vergaderingen/`
  (meeting documents per year).
