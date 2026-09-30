# Architecture

The deterministic engine in `app/cases/engine.py` chooses the outcome. A model, when one is configured, may only phrase text that the engine already decided. Without an API key the reply is the template.

## Data

- Local default: SQLite fixture in `data/`, built by `app/bank/fixture.py`. The transactions table contains an `is_fraud` column as a trap. The column list in `app/bank/access.py` does not select it.
- Postgres: `DATABASE_URL` as role `app_rw`. `app/db.py` sets `statement_timeout=15s` and `search_path=app,public` (no space; libpq splits connection options on spaces), and refuses a superuser or `BYPASSRLS` role. The eval schema is not queried.
- Health: `GET /health` and `GET /healthz` return the same JSON. Cloud Run probes use `/health` because the run.app front end reserves `/healthz`.
- `fraud_features` has no `customer_key`. The read joins `transactions` so a feature row is returned only for that customer’s charge.
- Operational tables live in the `app` schema (SQLite uses the same names). Audit tables are append-only. A correction inserts a row with `supersedes_audit_id`. KPIs read `audit_current`, the tip of each chain. The Python store rejects `UPDATE` on audit tables and any `DELETE`.

## Eval

`eval_run_id` and `case_source` are stored only when `EVAL_RUNNER_TOKEN` matches. `is_eval_case` is true when either value is stored. Metrics exclude those rows unless `include_eval=true`.

## Time

Display uses `transaction_ts_utc` and `customers.tz`. A country fallback exists only when `tz` is missing. Mexico is not treated as Mexico City when `tz` is `America/Tijuana`.
