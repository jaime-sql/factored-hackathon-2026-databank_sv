# Dispute-intake data pipeline (Factored AI & Data Hackathon 2026)

Use case: transaction-level dispute intake ("I don't recognize this charge").
**Pending / Reversed** charges get deterministic rule-based explanations. **Every other charge** (Approved, Declined) goes to an
ML fraud-triage model (gradient-boosted trees) compared against the baseline rule `fraud_score >= 30`, with label `is_fraud`.

## Run
```bash
cd /workspace/hackathon-data
bash pipeline/run_all.sh               # local: bronze -> silver -> gold -> fixture + SQLite slice -> tests -> parquet export
bash pipeline/run_all.sh --databricks  # plus load of masked gold + masked bronze/silver into Databricks (needs DATABRICKS_TOKEN in env)
uv run --no-project --python 3.12 --with-requirements pipeline/requirements.txt python pipeline/databricks_load.py --layers-only  # masked bronze/silver only
```
**Environment, from a clean checkout:** nothing pre-installed is needed besides `uv` *or* `python3`. Dependencies are pinned in
`pipeline/requirements.txt`. If `uv` is on PATH, every step runs as `uv run --no-project --python 3.12 --with-requirements pipeline/requirements.txt python`
(uv downloads Python 3.12 and builds a cached env on first use). Without uv, the script creates `.venv` with `python3 -m venv` and
`pip install -r pipeline/requirements.txt`. No step writes to Supabase, S3, or (without `--databricks`) Databricks; `load_supabase.py` is separate.
After every step and test succeeds, the script writes `out/last_run.json` (UTC finish time, duration, Python version, requirements hash,
app-slice row counts). `trust_check.py` uses it for the "reproducible" check.

Inputs: `raw/` (local copy of `s3://factored-datathon-2026-s3-157725502942-us-east-2-an/data/`), `.env` with `PSEUDO_SALT`
(gitignored, chmod 600). Local warehouse: `cache/pipeline.duckdb` (gitignored). Seed: `20260929`. A full run takes about 1.5–2 min.
Re-running with the same salt reproduces identical split hashes; this was verified on a clean rebuild.

## Lineage
| layer | objects | notes |
|---|---|---|
| bronze (`bronze.py`) | `bronze.transactions` (1,097 daily CSVs), `bronze.customers`, `bronze.products` | all columns VARCHAR exactly as delivered, plus `_source_file`, `_loaded_at`. Unmasked table **local only** (contains PII); a masked copy goes to Databricks (below). |
| silver (`silver.py` + `contract.py`) | `silver.transactions`, `silver.customers`, `silver.products`, `silver._run_log` | contract-checked, typed, countries normalized, deduped, `transaction_ts_utc` / `transaction_ts_local` added. Unmasked table **local only** (raw ids and exact lat/long); a masked copy goes to Databricks (below). |
| gold (`gold.py`) | `gold.transactions_masked`, `gold.customers_masked`, `gold.fraud_features` (+ `split`), `splits_manifest.json` | masked and pseudonymous. Loaded to Databricks. |
| app (`app_outputs.py`) | `fixtures/synthetic_duplicates.{parquet,csv}`, `app_slice.sqlite` | derived from gold only |
| cloud (`export.py`, `databricks_load.py`) | `workspace.gold.{transactions_masked, customers_masked, fraud_features, fraud_splits, synthetic_duplicates}` | Parquet → UC volume `workspace.gold.landing` (Files API) → Delta via SQL Statement API on "Serverless Starter Warehouse" |
| cloud, masked layers (`export.run_layers`, `databricks_load.run_layers`) | `workspace.bronze.{transactions,customers,products}_masked`, `workspace.silver.{transactions,customers,products}_masked`, `workspace.silver.run_log` | masked Parquet under `out/{bronze,silver}/` → PII scan gate → volumes `workspace.{bronze,silver}.landing` → Delta (same path as gold) |

Row counts: bronze/silver transactions 4,425,008, customers 150,000, products 400,000. Silver dedupe dropped 0 exact duplicates and found 0 PK conflicts.
Gold: transactions_masked 4,425,008; customers_masked 150,000; fraud_features 4,291,915 (ML scope = not Pending/Reversed).
Databricks (verified with `count(*)` after load): transactions_masked 4,425,008; customers_masked 150,000; fraud_features 4,291,915;
fraud_splits 4,291,915; synthetic_duplicates 600.
Databricks masked bronze/silver (loaded 2026-10-03, each `count(*)` equal to the local DuckDB count, see `out/databricks_load_layers.json`):
bronze transactions_masked 4,425,008, customers_masked 150,000, products_masked 400,000; silver transactions_masked 4,425,008,
customers_masked 150,000, products_masked 400,000, run_log 1. No unmasked bronze/silver row goes to the cloud.

### Masked bronze/silver copies (`export.run_layers`)
- Explicit column allow-list per table; raw ids → the same salted `customer_key` / `product_key` / `transaction_key` as gold
  (bronze hashes `nullif(trim(id), '')`, so keys join across all three layers; the export asserts every `customer_key` exists in gold).
- Dropped: customers `document_number, document_type, first_name, last_name, date_of_birth, gender, email, mobile_phone, landline_phone,
  address, city, state, postal_code`; products `product_number`; transactions `latitude, longitude`. Bronze `_source_file` is cut to the
  path relative to `raw/` (no local paths).
- Kept (not direct identifiers): customer `country, detected_accent, segment, credit_score, estimated_monthly_income, occupation,
  marital_status, education_level, registration_date, registration_branch_id, customer_status, last_updated, accepts_marketing`;
  all product and transaction business columns. Bronze stays all-VARCHAR as delivered; silver keeps contract types.
- Upload gate (`export.scan_masked_parquet`, full scan of every file): no PII column names; every `*_key` matches `PREFIX_[0-9a-f]{20}`;
  no string value matching a raw id (`CLI-/PRD-/TRX-…`), an email, an international phone, a local path, or any known document number,
  phone, address, full name, last name or product number. Any failure raises before upload.

## Schema contract (silver)
`contract.py` defines, per table, the exact column set and types, NOT NULL columns, enums and ranges. `silver.py` raises `ContractError` on:
- column drift (any missing or extra column vs contract);
- any non-empty bronze value that fails to cast to its contract type;
- NULLs in NOT NULL columns; enum violations (`transaction_status` ∈ Approved/Declined/Pending/Reversed, `currency` ∈ MXN/COP/ARS/USD,
  `channel`, `transaction_type`, customer `segment`, customer `country` ∈ Mexico/Colombia/Argentina); `fraud_score` outside [0,100];
  `credit_score` outside [300,850];
- an unmapped country label (map: `México`→`Mexico`; also accepts Mexico, Colombia, Argentina, Brazil, Spain, USA);
- the timestamp-offset assumption breaking (see below).

**Timestamp offset (recorded in `common.TS_OFFSET_HOURS = 6` and `silver._run_log`):** raw `transaction_date` falls 6 h to 30 h after
00:00 of `process_date`, i.e. it's UTC while `process_date` is a UTC-6 local day. Silver keeps `transaction_ts_utc` (raw) and
`transaction_ts_local = utc − 6h`, which always lands in [process_date 00:00, process_date+1 00:00]. 51 rows sit exactly on the
closing midnight boundary. The offset is fixed for all countries (it doesn't follow real AR/CO/MX zones).

**Dedupe rule:** drop exact duplicates. On a PK conflict keep the latest-arriving version (max `process_date`, then source file) and log it.

## Masking rules (gold)
- `customer_id` → `customer_key` = `'CUS_' || left(sha256(salt || ':customer:' || id), 20)`. Same pattern for `product_key` (`PRD_`) and
  `transaction_key` (`TXN_`), with a different prefix inside the hash input so the keys can't be linked across kinds. The salt is only in `.env`.
- Dropped: names, document number/type, date of birth, gender, email, phones, address, postal code, customer city/state, product number,
  IPs (digital_events not in gold), exact `latitude`/`longitude`.
- Location is coarsened to `transaction_country` + `transaction_city`.
- Kept for fairness slices: `customer_country`, `customer_segment`, `customer_accent` (null → `unknown`).
- Every gold row carries `customer_key`. Access goes through `access.get_transactions(customer_key)` (below).
- `gold.transactions_masked` is built from an explicit column allow-list (`gold.MASKED_COLUMNS`); the build asserts the output schema matches it exactly.

## Fraud-triage modeling table (`gold.fraud_features`)
- Scope: `transaction_status NOT IN ('Pending','Reversed')` (these rows go to the rules). The status filter only picks rows; it's not a feature.
- Label `is_fraud`; baseline `baseline_flag = coalesce(fraud_score >= 30, false)`; `fraud_score` is also a feature.
- Numeric features: amount, log_amount, amount_usd, fraud_score, local_hour, local_dow, is_night, is_weekend, is_cross_border
  (transaction country ≠ customer country), customer_tenure_days, product_tenure_days, prior_tx_count, prior_tx_count_1h,
  prior_tx_count_24h, prior_tx_count_7d, secs_since_prev_tx, prior_mean_amount_same_ccy, amount_to_prior_mean,
  prior_count_same_merchant, prior_cross_border_count_30d.
- Categorical features: currency, channel, transaction_type, transaction_category, merchant_category, merchant_name, transaction_country,
  transaction_city, product_type.
- Slice columns (for fairness evaluation, **not features**): customer_country, customer_segment, customer_accent.
- History aggregates run over all of the customer's transactions (any status) with window frames ending `1 SECOND PRECEDING`,
  so only **strictly earlier** timestamps count (timestamps have second precision). Prior labels and prior statuses are never aggregated.
- **Excluded:** transaction_status, response_code (set by the authorization decision), is_fraud (label only), latitude/longitude,
  product snapshot fields (current_balance, product_status, last_transaction_date, days_past_due, last_updated, credit_limit, has_linked_app),
  customer snapshot fields (credit_score, estimated_monthly_income, customer_status, last_updated), any complaint/interaction/survey join,
  any aggregate over prior labels or statuses, and any aggregate that includes same-or-later timestamps.

### Time-based split (70/15/15 by row count, cut on `transaction_ts_utc`)
| split | rule (UTC) | rows | positives (is_fraud) | baseline flagged | baseline TP | baseline precision | baseline recall | sha256 of sorted transaction_key |
|---|---|---|---|---|---|---|---|---|
| train | ts < 2025-07-26 00:30:11 | 3,004,340 | 3,028 | 2,071 | 1,650 | 0.7967 | 0.5449 | `8c85d3bb41ce96c6188980815f14bdfb6a1facf3c423a7c9dd097797add64584` |
| val | 2025-07-26 00:30:11 ≤ ts < 2026-01-07 00:26:41 | 643,787 | 599 | 413 | 325 | 0.7869 | 0.5426 | `8cc3b47d7c907dc48acaf50b6c3c5ce710999a4a1c2165cec3053ffe9266de14` |
| test | ts ≥ 2026-01-07 00:26:41 | 643,788 | 574 | 422 | 334 | 0.7915 | 0.5819 | `fbc11459459e44e9f07aac3d78fa755d33a0aea70f2559f69ee0780d6397390a` |

The same cutoffs in America/Guatemala (CST, UTC-6) are 2025-07-25 18:30:11 and 2026-01-06 18:26:41. The hash is SHA-256 over the sorted
`transaction_key`s, each followed by `\n`. Full details are in `../splits_manifest.json`.

## Synthetic duplicate-charge fixture
`fixtures/synthetic_duplicates.{parquet,csv}`: 300 cases / 600 rows (seed 20260929). Source rows are Approved, merchant-bearing masked gold
rows of app-slice customers. Each case has an `original` and a `repeat` row with the same customer_key, merchant, amount and product.
- `true_duplicate` (181 cases): repeat 5–180 s later, same channel.
- `legitimate_repeat` (119 cases): repeat 5–30 min later, and in half of these cases a different channel.

Every row has `is_synthetic = true`, `scenario`, `case_id`, `source_transaction_key`, `is_fraud = NULL`, and new keys `SYN_####_A/B`,
so they never appear in `fraud_features` or its splits (tested). The labels are true by construction only; the real data contains 0 duplicate charges
(see `../data-quality.md`).

## App slice (`app_slice.sqlite`, 13.8 MB)
1,091 pseudonymous customers (Argentina 367, Colombia 364, Mexico 360). Per country the pick is deterministic: 150 with a Pending tx,
100 with a Reversed tx, 100 with fraud_score ≥ 30, and 150 random (overlaps merged).
40,322 transactions: Approved 36,967, Declined 1,943, Pending 929, Reversed 483; fraud_score ≥ 30: 308; < 10: 10,640; is_fraud: 261.
Tables: `customers`, `transactions`, `synthetic_duplicates` (all `is_synthetic=1`), `meta`. Contains no raw ids or PII (tested).

## Tests (all PASS on the final run)
- `tests/test_leakage.py`
  - split ordering (no val/test timestamp earlier than the train cutoff; no test timestamp before the val cutoff; max(train) < min(test))
  - fraud_features columns equal the allow-list exactly, with no forbidden column
  - no Pending/Reversed in ML scope
  - manifest hashes recompute
  - 300 sampled rows: history features recomputed by brute force over strictly-earlier rows match
  - synthetic keys absent from fraud_features
- `tests/test_isolation.py`
  - 60 sampled customers only ever get their own rows, and the row counts equal a direct count
  - two customers' results are disjoint
  - 20 forged, well-formed random `CUS_` keys return []
  - malformed or injection keys are rejected with `AccessError`: `CUS_%`, `' OR '1'='1`, a valid key plus `' OR customer_key IS NOT NULL --`, uppercase, whitespace, newline, a raw `CLI-…` id, `*`, non-hex, None, int, list
  - using another customer's key never returns the caller's rows
  - the same checks run on the SQLite slice
- `tests/test_pii.py`
  - no PII column names in gold, the exported Parquet, the fixture or the SQLite slice
  - no raw CLI-/PRD-/TRX- ids, emails, document numbers or phone numbers in any string value
  - the slice is < 50 MB and all fixture rows are synthetic

## Data access
`access.get_transactions(customer_key, backend="duckdb"|"sqlite")` validates the key against `^CUS_[0-9a-f]{20}$`, runs a
parameterized `WHERE customer_key = ?` on a read-only connection, and post-checks every returned row's key.

## Supabase load (`load_supabase.py`, `supabase_schema.sql`)
Target: project `factored-hackathon-2026` (ref `dmqwgbtrrnxkgcahunrc`, us-east-2). The script refuses any URL that doesn't reference this ref,
and always refuses `iglesiaSJB` (`kwbhytabavegnqfeidjw`).
```bash
export SUPABASE_DB_URL='postgresql://...'     # session-pooler or direct URI; supply at runtime, never commit
.venv/bin/python pipeline/load_supabase.py --dry-run   # source counts + PII scan only
.venv/bin/python pipeline/load_supabase.py             # apply schema (idempotent), truncate, COPY, verify counts/coverage/RLS
```
- Tables in `public`:
  - `customers` (1,091)
  - `transactions` (40,322; **no `is_fraud`**)
  - `synthetic_duplicates` (600 rows / 300 cases; `is_synthetic = 1` enforced by a CHECK)
  - `meta` (4)
  - `fraud_features` (38,910 = every Approved/Declined slice transaction; Pending 929 and Reversed 483 have none). Its columns are
    `transaction_key` (PK, FK → transactions) + the 29 features in `hack-ml/artifacts/feature_list.json` + `split`; no label.
- `eval.transaction_labels(transaction_key PK/FK, is_fraud boolean)` has 40,322 rows, of which 261 are true.
  `eval` is not an API-exposed schema, and anon/authenticated/console_readonly have no USAGE on it. Only service_role (and postgres) can read it.
- Reserved for the AI/ML engineers (not created): `eval.case_labels` keyed by `case_id`.
- RLS is on for all 6 tables. There are no anon/authenticated policies, and those roles' table grants are revoked.
  `eval.transaction_labels` has a restrictive deny-all policy.
- `console_readonly` is a NOLOGIN role with USAGE on `public`, SELECT on the 5 public tables, and `USING (true)` SELECT policies on them.
  Grant it to a login role when needed.
- fraud_features is taken from the local `gold.fraud_features`, which has the same content and counts as Databricks `workspace.gold.fraud_features`.
- Tested end-to-end (twice, idempotent) on a local Postgres 17 with Supabase-like roles. All counts matched, anon was denied,
  console_readonly read public but was denied on eval.
- Why the script exists: the Supabase MCP connector only takes inline SQL. The transactions alone are about 10 MB of random-key data,
  which can't be pushed through `execute_sql` reliably, so the bulk load has to run client-side.
- **Timestamps (migration `timestamps_to_timestamptz`, 2026-09-29):** `transaction_ts_utc` and `transaction_ts_local` are `timestamptz`;
  `process_date` is `date`. This applies to both `transactions` and `synthetic_duplicates`.
  - `transaction_ts_utc` source text is parsed as UTC.
  - `transaction_ts_local` source text is UTC-6 wall-clock time, so it's parsed with `-06` and stores the *same instant* as `transaction_ts_utc`.
    Use `transaction_ts_utc AT TIME ZONE 'America/Guatemala'` (or `'-06'`-shifted math) to get the local clock.
  - The loader builds tz-aware Python datetimes, so the result doesn't depend on the session `TimeZone`.
  - Tested twice on a local Postgres 17, starting from the old text schema: all counts matched, 0 NULLs, and utc = local instants on all rows.
  - Every transaction's local day equals `process_date`. 6 synthetic `repeat` rows cross local midnight but keep the original's `process_date`
    (a fixture artifact).
- **Customer time zone (migration `customers_tz`, 2026-09-29):** `public.customers.tz` is text, NOT NULL, and CHECK-restricted to the allowed zones (now 4).
  `customer_country` is CHECK-restricted to Argentina/Colombia/Mexico. The loader derives tz from `COUNTRY_TZ`: Argentina →
  America/Argentina/Buenos_Aires, Colombia → America/Bogota, Mexico → America/Mexico_City. It exits on any unmapped country.
  - Migration `customers_tz_add_tijuana`: a city override from local silver.customers (joined via the salted key; the city is never loaded)
    sets Tijuana → America/Tijuana (50 MX customers). The constraint now allows 4 zones. Distribution: Buenos_Aires 367, Bogota 364, Mexico_City 310, Tijuana 50.
  - 1,841 of 40,322 slice transactions are cross-border (transaction_country ≠ customer_country). They are displayed in the customer's zone for now.
