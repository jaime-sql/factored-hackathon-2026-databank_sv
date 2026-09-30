# Harbor Desk

Factored AI & Data Hackathon 2026 repository `factored-hackathon-2026-databank_sv`.

Transaction-level dispute intake for a LATAM card portfolio (Mexico, Colombia, Argentina). A customer picks one charge — “No reconozco este cargo” or “Não reconheço esta cobrança” — and the desk explains it, offers a card block only after confirmation, or hands the case to a person. The assistant never moves money.

Portuguese copy is machine-translated and is reported as `language=pt`, not as production traffic.

## Run locally

SQLite is the default. No API key is required. From a fresh clone:

```bash
uv sync --all-groups
make dev
```

Open [http://127.0.0.1:8091](http://127.0.0.1:8091). The other pages are `/agent` and `/metrics`.

`GET /health` is the health check. `GET /healthz` returns the same JSON. On Cloud Run, probe `/health`: the run.app front end reserves `/healthz` and answers 404 before the container.

`make check` runs ruff, mypy, and pytest.

SQLite uses the synthetic fixture in `app/bank/fixture.py`. With `DATABASE_URL` set, the personas map to real challenge-data customers. The demo database is not in git. Startup builds `data/bank.sqlite` and `data/ops.sqlite`. `data/` is gitignored. There is nothing to download.

## Postgres

`DATABASE_URL` is read from the environment only. Leave it empty for SQLite. Never commit a real URL.

The app connects as the `app_rw` role: read public data tables, no writes to them, no access to `eval`, statement timeout 15 seconds. Apply `migrations/001_app_schema.sql` yourself as the owner. The app does not run that file. On Cloud Run the URL belongs in Secret Manager; `deploy/cloudrun.sh` uploads the environment value into a secret and passes the secret name, not the URL, to the service.

Model features are read from `public.fraud_features` joined to the customer’s transaction. Pending and Reversed charges have no feature row. If any other status has no feature row, the desk routes it to REVIEW and never LOW.

## Eval runner

`POST /cases` accepts optional `eval_run_id` and `case_source` (`sample`, `synthetic_dup`, `red_team`, `ood_sv_text`, `pt_translated`) only when the `EVAL_RUNNER_TOKEN` header matches the environment value. Without that header the fields are stored as null. Case ids are server-generated text UUIDs. Both fields are on the case, on each audit row, and on `app.audit_current`, which the runner joins to its labels.

The metrics page excludes eval traffic by default. The toggle is labeled “Demo sample (fraud-enriched, ~11x HIGH rate vs full data)”.

## Routing

1. `fraud_score > 30` is HIGH for every status, including Pending and Reversed. The desk offers a card block and performs it only after an explicit confirmation, then hands off.
2. Otherwise Pending and Reversed get a fixed explanation and a prominent “Sigo sin reconocer este cargo” / “Continuo sem reconhecer esta cobrança” action (`handoff_reason=customer_contests_rule_answer`).
3. Otherwise a missing feature row is REVIEW, never LOW.
4. Otherwise the vendored LightGBM model returns REVIEW or LOW. LOW explains the merchant from history. A synthetic duplicate is labeled synthetic.

Times shown to the customer and in the handoff packet are `transaction_ts_utc` converted with `customers.tz` (Buenos Aires, Bogotá, Mexico City, Tijuana). `is_fraud` is never read.
