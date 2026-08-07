-- Cash ledger: every cash movement on the club's brokerage account, so the
-- cash balance is derivable without the xlsx meeting sheets.
-- Apply once in the Supabase SQL editor of project nkxoqzbkhetdfeaqgmaw.

create table if not exists cash_ledger (
  id bigint generated always as identity primary key,
  txn_date date not null,
  kind text not null check (kind in ('dividend','deposit','withdrawal','fee','trade_buy','trade_sell','seed','other')),
  amount_eur numeric not null,       -- signed: positive = cash in, negative = cash out
  description text,
  source text not null,              -- 'binck' | 'bolero' | 'seed' | 'manual'
  created_at timestamptz not null default now(),
  unique (source, txn_date, kind, amount_eur, description)
);
create index if not exists cash_ledger_date_idx on cash_ledger (txn_date);
