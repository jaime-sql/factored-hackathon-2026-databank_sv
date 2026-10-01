# Decisions

- HIGH (`fraud_score > 30`) runs before the Pending and Reversed explanations, including when those charges have no feature row.
- A missing feature row on any other status is REVIEW, never LOW. Auto-close is not allowed without a model score.
- Audit history is append-only. `is_test` is written only at insert time. `test_cases` is insert and select only. Case and handoff rows may be updated. Nothing is deleted. `audit_current` stays unfiltered for the eval runner. Desk metrics read `audit_live`.
- Eval fields are ignored unless the runner presents `EVAL_RUNNER_TOKEN`. The metrics default hides that traffic and labels the include toggle as a fraud-enriched demo sample. `include_eval` and `include_test` are honored only for the admin token.
- `QA_TEST_TOKEN` marks a browser session as test traffic (`is_test` at insert time) via the `X-Test-Token` header or `POST /api/test-mode`. The token is not accepted in the URL. Empty disables it. Eval runs never set the flag. Older demo ids go in `test_cases`; `--before` skips eval runs and the script reports the inserted row count. Metrics and the audit export read `audit_live` unless an admin asks to include test or eval rows from `audit_current`. If that schema is missing, those reads use `audit_current` and `/health` reports `migrations_ok: false`. The token value is not stored in the repo.
- The console does not compute label-based safe or unsafe rates. Those need `eval.case_labels`, which `app_rw` cannot read.
- `DATABASE_URL` stays in the environment and in Secret Manager. It is not committed.
