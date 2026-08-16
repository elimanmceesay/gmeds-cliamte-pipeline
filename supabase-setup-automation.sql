-- Run once in the SAME Supabase project (Project → SQL Editor → New query → Run).
-- Adds two tables on top of climate_factors:
--   climate_readings — structured time-series data the scraper can fetch cleanly
--   climate_alerts   — a review queue for anything that needs a human's eyes
--                      before it changes what the dashboard says (new reports,
--                      policy announcements, disaster bulletins)

create table climate_readings (
  id bigint generated always as identity primary key,
  metric text not null,          -- e.g. 'reliefweb_reports_7d', 'debt_gdp_pct', 'cbg_policy_rate'
  value numeric,
  value_text text,               -- for non-numeric readings
  observed_at date not null default current_date,
  source text not null,
  fetched_at timestamptz not null default now(),
  unique (metric, observed_at, source)
);

create table climate_alerts (
  id bigint generated always as identity primary key,
  headline text not null,
  summary text,
  url text,
  source text not null,          -- 'ReliefWeb', 'World Bank', 'IMF', 'CBG', ...
  detected_at timestamptz not null default now(),
  reviewed boolean not null default false,
  reviewed_at timestamptz,
  unique (headline, source)
);

alter table climate_readings enable row level security;
create policy "anyone can read readings" on climate_readings for select using (true);
create policy "anyone can write readings" on climate_readings for insert with check (true);
create policy "anyone can update readings" on climate_readings for update using (true);

alter table climate_alerts enable row level security;
create policy "anyone can read alerts" on climate_alerts for select using (true);
create policy "anyone can write alerts" on climate_alerts for insert with check (true);
create policy "anyone can update alerts" on climate_alerts for update using (true);
