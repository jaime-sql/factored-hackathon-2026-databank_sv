-- Supabase schema for the dispute-intake demo (project factored-hackathon-2026). Idempotent.
-- public: masked app slice (no labels). eval: labels, NOT exposed via the Data API.
create schema if not exists eval;

create table if not exists public.customers (
  customer_key text primary key,
  customer_country text, customer_segment text, customer_accent text, slice_reason text,
  tz text not null);

create table if not exists public.transactions (
  transaction_key text primary key,
  customer_key text not null references public.customers(customer_key),
  product_key text, product_type text, transaction_type text, transaction_category text, currency text, channel text,
  branch_id text, merchant_name text, merchant_category text, transaction_country text, transaction_city text,
  transaction_status text, response_code text, customer_country text, customer_segment text, customer_accent text,
  transaction_ts_utc timestamptz, transaction_ts_local timestamptz, process_date date,
  amount double precision, amount_usd double precision, fraud_score double precision);   -- is_fraud moved to eval.transaction_labels
create index if not exists ix_transactions_customer_ts on public.transactions (customer_key, transaction_ts_utc desc);
create index if not exists ix_transactions_status on public.transactions (transaction_status);

create table if not exists public.synthetic_duplicates (
  transaction_key text primary key,
  case_id text not null, scenario text, role text, is_synthetic bigint, seconds_after_original bigint, source_transaction_key text,
  customer_key text not null references public.customers(customer_key),
  product_key text, product_type text, transaction_ts_utc timestamptz, transaction_ts_local timestamptz, process_date date,
  transaction_type text, transaction_category text, amount double precision, currency text, amount_usd double precision,
  channel text, branch_id text, merchant_name text, merchant_category text, transaction_country text, transaction_city text,
  transaction_status text, response_code text, is_fraud text, fraud_score double precision,
  customer_country text, customer_segment text, customer_accent text,
  constraint synthetic_only check (is_synthetic = 1));
create index if not exists ix_syndup_customer on public.synthetic_duplicates (customer_key);
create index if not exists ix_syndup_case on public.synthetic_duplicates (case_id);

create table if not exists public.meta (key text primary key, value text);

create table if not exists public.fraud_features (
  transaction_key text primary key references public.transactions(transaction_key) on delete cascade,
  amount numeric(15,2), log_amount double precision, amount_usd numeric(15,2), fraud_score numeric(5,2),
  local_hour bigint, local_dow bigint, is_night integer, is_weekend integer, is_cross_border integer,
  customer_tenure_days bigint, product_tenure_days bigint, prior_tx_count bigint, prior_tx_count_1h bigint,
  prior_tx_count_24h bigint, prior_tx_count_7d bigint, secs_since_prev_tx bigint, prior_mean_amount_same_ccy double precision,
  amount_to_prior_mean double precision, prior_count_same_merchant bigint, prior_cross_border_count_30d numeric(38,0),
  currency text, channel text, transaction_type text, transaction_category text, merchant_category text, merchant_name text,
  transaction_country text, transaction_city text, product_type text,
  split text not null check (split in ('train','val','test')));
create index if not exists ix_fraud_features_split on public.fraud_features (split);

create table if not exists eval.transaction_labels (
  transaction_key text primary key references public.transactions(transaction_key) on delete cascade,
  is_fraud boolean not null);
comment on schema eval is 'Evaluation labels. Not exposed via the Data API; no anon/authenticated/console_readonly access. Reserved: eval.case_labels (keyed by case_id), owned by the AI/ML engineers; not created here.';

-- RLS on every table; no anon/authenticated policies (server-side service_role/postgres only).
alter table public.customers enable row level security;
alter table public.transactions enable row level security;
alter table public.synthetic_duplicates enable row level security;
alter table public.meta enable row level security;
alter table public.fraud_features enable row level security;
alter table eval.transaction_labels enable row level security;

-- Belt and braces: remove Data API role grants on these tables
revoke all on public.customers, public.transactions, public.synthetic_duplicates, public.meta, public.fraud_features from anon, authenticated;
revoke all on schema eval from public, anon, authenticated;
revoke all on all tables in schema eval from public, anon, authenticated;
alter default privileges in schema eval revoke all on tables from public, anon, authenticated;

-- Read-only console role (NOLOGIN; grant it to a login role when needed)
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'console_readonly') then
    create role console_readonly nologin;
  end if;
end $$;
grant usage on schema public to console_readonly;
grant select on public.customers, public.transactions, public.synthetic_duplicates, public.meta, public.fraud_features to console_readonly;
revoke all on schema eval from console_readonly;
revoke all on all tables in schema eval from console_readonly;

drop policy if exists console_readonly_select on public.customers;
create policy console_readonly_select on public.customers for select to console_readonly using (true);
drop policy if exists console_readonly_select on public.transactions;
create policy console_readonly_select on public.transactions for select to console_readonly using (true);
drop policy if exists console_readonly_select on public.synthetic_duplicates;
create policy console_readonly_select on public.synthetic_duplicates for select to console_readonly using (true);
drop policy if exists console_readonly_select on public.meta;
create policy console_readonly_select on public.meta for select to console_readonly using (true);
drop policy if exists console_readonly_select on public.fraud_features;
create policy console_readonly_select on public.fraud_features for select to console_readonly using (true);

-- Explicit deny on labels (silences lint 0008 without granting anything); server-side service_role access to eval.
drop policy if exists deny_all on eval.transaction_labels;
create policy deny_all on eval.transaction_labels as restrictive for all to public using (false) with check (false);
grant usage on schema eval to service_role;
grant select, insert, update, delete on eval.transaction_labels to service_role;
alter default privileges in schema eval grant select, insert, update, delete on tables to service_role;

-- Migration timestamps_to_timestamptz (2026-09-29): timestamps as timestamptz, process_date as date.
-- transaction_ts_utc: source text is UTC. transaction_ts_local: source text is UTC-6 wall clock -> parsed with -06 (same instant as utc).
-- Converts only if a column is still text (databases created from an older version of this file).
do $$
declare t text;
begin
  foreach t in array array['transactions','synthetic_duplicates'] loop
    if (select data_type from information_schema.columns where table_schema='public' and table_name=t and column_name='transaction_ts_utc') = 'text' then
      execute format('alter table public.%I
        alter column transaction_ts_utc type timestamptz using (transaction_ts_utc || ''+00'')::timestamptz,
        alter column transaction_ts_local type timestamptz using (transaction_ts_local || ''-06'')::timestamptz,
        alter column process_date type date using process_date::date', t);
    end if;
  end loop;
end $$;
comment on column public.transactions.transaction_ts_utc is 'Transaction instant (source transaction_date, UTC).';
comment on column public.transactions.transaction_ts_local is 'Same instant; source value was UTC-6 wall-clock time, parsed with -06 offset.';
comment on column public.transactions.process_date is 'Processing day in UTC-6 (local calendar date).';
comment on column public.synthetic_duplicates.transaction_ts_utc is 'Transaction instant (UTC).';
comment on column public.synthetic_duplicates.transaction_ts_local is 'Same instant; source value was UTC-6 wall-clock time, parsed with -06 offset.';
comment on column public.synthetic_duplicates.process_date is 'Processing day in UTC-6 (local calendar date).';

-- Migration customers_tz (2026-09-29): IANA zone per customer, derived from customer_country by load_supabase.py.
alter table public.customers add column if not exists tz text;
update public.customers set tz = case customer_country when 'Argentina' then 'America/Argentina/Buenos_Aires'
  when 'Colombia' then 'America/Bogota' when 'Mexico' then 'America/Mexico_City' end where tz is null;
alter table public.customers alter column tz set not null;
alter table public.customers drop constraint if exists customers_tz_allowed;
alter table public.customers add constraint customers_tz_allowed check (tz in ('America/Argentina/Buenos_Aires','America/Bogota','America/Mexico_City','America/Tijuana'));
alter table public.customers drop constraint if exists customers_country_allowed;
alter table public.customers add constraint customers_country_allowed check (customer_country in ('Argentina','Colombia','Mexico'));
-- Migration customers_tz_add_tijuana: tz = city override (Tijuana -> America/Tijuana) from local customer records, else country default.
comment on column public.customers.tz is 'IANA zone of the customer''s local clock: city override from local customer records (Tijuana -> America/Tijuana), else country default (AR Buenos_Aires, CO Bogota, MX Mexico_City). City itself is not stored.';

-- app_rw: the app's login role (password is set out of band, never committed)
-- create role app_rw login noinherit password '<set out of band>';
-- alter role app_rw set statement_timeout = '15s';
create schema if not exists app;
revoke all on schema app from public, anon, authenticated;
grant usage on schema public, app to app_rw;
grant select on public.customers, public.transactions, public.fraud_features, public.synthetic_duplicates, public.meta to app_rw;
-- plus: create policy app_rw_select ... for select to app_rw using (true) on each public table
alter default privileges for role postgres in schema app grant select, insert, update on tables to app_rw;
alter default privileges for role postgres in schema app grant usage, select on sequences to app_rw;

-- eval_rw + eval.case_labels (Sep 29). Password set out of band.
-- create role eval_rw login noinherit password '<set out of band>'; alter role eval_rw set statement_timeout='60s';
create table if not exists eval.case_labels(
  case_id text primary key,
  transaction_key text references public.transactions(transaction_key),
  eval_run_id text not null,
  case_source text not null check (case_source in ('sample','synthetic_dup','red_team','ood_sv_text','pt_translated')),
  is_fraud boolean,
  expected_decision text check (expected_decision in ('rule_explain','block_handoff','handoff','auto_resolve')),
  outcome_correct boolean, wrong_autoclose boolean, wrongful_block boolean,
  pii_leak boolean, injection_attempt boolean, injection_success boolean,
  groundedness numeric check (groundedness between 0 and 1),
  labeled_at timestamptz not null default now());
alter table eval.case_labels enable row level security;
-- deny_all (restrictive) on eval.* now targets anon, authenticated, console_readonly, app_rw.
-- eval_rw: SELECT eval.transaction_labels, public.transactions, public.customers; ALL on eval.case_labels; USAGE on app.
