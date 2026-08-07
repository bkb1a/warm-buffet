-- warm-buffet: investment club portfolio & news agent
-- Apply once in the Supabase SQL editor of project nkxoqzbkhetdfeaqgmaw.

create table if not exists holdings (
  id bigint generated always as identity primary key,
  name text not null unique,
  ticker text,
  currency text not null default 'EUR',
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- One row per holding per meeting sheet in 't Warm Buffet Rendement.xlsx
create table if not exists snapshots (
  id bigint generated always as identity primary key,
  meeting_date date not null,
  holding_name text not null,
  currency text,
  shares numeric,
  price numeric,
  prev_price numeric,
  value_eur numeric,
  weight numeric,
  return_since_prev numeric,
  purchase_price numeric,
  purchase_value_eur numeric,
  unrealized_pnl_eur numeric,
  unrealized_pnl_pct numeric,
  created_at timestamptz not null default now(),
  unique (meeting_date, holding_name)
);

-- Portfolio-level totals per meeting
create table if not exists portfolio_totals (
  id bigint generated always as identity primary key,
  meeting_date date not null unique,
  securities_value_eur numeric,
  cash_eur numeric,
  total_value_eur numeric,
  eur_exposure numeric,
  usd_exposure numeric,
  return_portfolio numeric,
  return_sp500 numeric,
  return_msci_world numeric,
  return_eurostoxx50 numeric,
  created_at timestamptz not null default now()
);

create table if not exists news_items (
  id bigint generated always as identity primary key,
  holding_name text not null,
  headline text not null,
  url text,
  source text,
  published_at date,
  summary text,
  sentiment text check (sentiment in ('positive','negative','neutral','mixed')),
  relevance text,
  fetched_at timestamptz not null default now(),
  unique (holding_name, url)
);

create table if not exists digests (
  id bigint generated always as identity primary key,
  generated_at timestamptz not null default now(),
  period_start date,
  period_end date,
  markdown_content text not null
);
