-- Weekly price history per ticker (avg of week open and week close).
-- Apply once in the Supabase SQL editor of project nkxoqzbkhetdfeaqgmaw.

create table if not exists prices_weekly (
  id bigint generated always as identity primary key,
  ticker text not null,
  week_start date not null,          -- Monday of the week
  avg_price numeric not null,        -- (week open + week close) / 2, split-adjusted (Yahoo)
  currency text not null,
  fetched_at timestamptz not null default now(),
  unique (ticker, week_start)
);
create index if not exists prices_weekly_ticker_idx on prices_weekly (ticker, week_start);
