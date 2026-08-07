-- Real broker transactions (Binck 2014-2021 + Bolero 2025-...).
-- Apply in the Supabase SQL editor of project nkxoqzbkhetdfeaqgmaw
-- (together with prices_weekly.sql if not applied yet).

create table if not exists transactions (
  id bigint generated always as identity primary key,
  txn_date date not null,
  side text not null check (side in ('buy','sell')),
  holding_name text not null,        -- canonical name (matches holdings.name) or raw for pre-club items
  raw_name text not null,            -- as it appears in the broker export
  shares numeric,                    -- null for Bolero rows (export lacks quantities)
  amount_eur numeric not null,       -- absolute transaction value in EUR
  price_eur numeric,                 -- amount / shares, when shares known
  source text not null check (source in ('binck','bolero')),
  created_at timestamptz not null default now(),
  unique (source, txn_date, raw_name, side, amount_eur)
);
