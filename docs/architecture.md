# Architecture

The deterministic engine in `app/cases/engine.py` chooses the outcome. A model, when one is configured, may only phrase text that the engine already decided. Without an API key the reply is the template.

## Data

- Local default: SQLite fixture in `data/`, built by `app/bank/fixture.py`. The transactions table contains an `is_fraud` column as a trap. The column list in `app/bank/access.py` does not select it.
- Postgres: `DATABASE_URL` as role `app_rw`. `app/db.py` sets `statement_timeout=15s` and `search_path=app,public` (no space; libpq splits connection options on spaces), and refuses a superuser or `BYPASSRLS` role. The eval schema is not queried.
- Health: `GET /health` and `GET /healthz` return the same JSON, including `migrations_ok`. Cloud Run probes use `/health` because the run.app front end reserves `/healthz`. When `is_test`, `test_cases`, or `audit_live` is missing, `migrations_ok` is false, case inserts omit `is_test`, test marks are ignored, and metrics read `audit_current`.
- `fraud_features` has no `customer_key`. The read joins `transactions` so a feature row is returned only for that customer’s charge.
- A `SYN_*_A` / `SYN_*_B` charge is not in `transactions` and has no `fraud_features` row. The other model features come from the `fraud_features` row of its `source_transaction_key`. This is a deliberate demo choice. Routing still reads the SYN row's own `fraud_score` and status: the HIGH rule uses that value, and the same value replaces `fraud_score` on the source feature payload before the model runs. Order stays fraud_score > 30, then Pending, then Reversed, then the model band. The duplicate explanation is only for a LOW band. Lucía's `SYN_0112` pair is the duplicate-route demo because its source scores LOW. María's `SYN_0238` pair routes to REVIEW by design.
- Operational tables live in the `app` schema (SQLite uses the same names). Audit tables are append-only: the app role has `INSERT` and `SELECT` only. A correction inserts a row with `supersedes_audit_id`. `audit_current` is the unfiltered tip of each chain and is what `eval_rw` reads. Desk KPIs read `audit_live`, which drops insert-time `is_test` rows, case ids in `test_cases`, and tips with `eval_run_id`. The Python store rejects `UPDATE` on audit tables and on `test_cases`, and any `DELETE`.

## Eval

`eval_run_id` and `case_source` are stored only when `EVAL_RUNNER_TOKEN` matches. `is_eval_case` is true when either value is stored. An eval run never sets `is_test`.

`QA_TEST_TOKEN` is optional. A matching `X-Test-Token` header, or a POST to `/api/test-mode` from the customer page, stores `is_test=true` on the case and on each audit row at insert time and keeps the flag in the signed session cookie. The token is not taken from the URL. A wrong token is a silent miss. Metrics and the audit export read `audit_live` unless the admin token is sent with `include_test=1` or `include_eval=1`, in which case they read `audit_current` and apply only the filters that were not requested. SQLite creates the columns, `test_cases`, and `audit_live` on startup. Postgres uses `migrations/002_is_test.sql` (applied on startup when the role can change the objects; otherwise the owner runs it). That file does not replace `audit_current` and does not change audit-table grants. `scripts/mark_demo_cases_test.py` inserts existing case ids into `test_cases` (`ON CONFLICT DO NOTHING`). `--before` skips rows with `eval_run_id`, and the printed count is the number of rows inserted. It does not change audit rows and it is not run on startup.

## Time

Display uses `transaction_ts_utc` and `customers.tz`. A country fallback exists only when `tz` is missing. Mexico is not treated as Mexico City when `tz` is `America/Tijuana`.
