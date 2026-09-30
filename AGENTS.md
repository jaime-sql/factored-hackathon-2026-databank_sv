# Working in this repo

- Customer text is redacted before it is logged. Do not select `is_fraud` or read the `eval` schema.
- Do not `UPDATE` or `DELETE` audit tables. Append a row with `supersedes_audit_id`.
- Case ids are `uuid.uuid4()` strings from the server. Do not accept a client case id.
- `eval_run_id` and `case_source` are stored only after `accept_eval_fields` checks `EVAL_RUNNER_TOKEN`.
- Thresholds are re-read from `triage/artifacts/thresholds.json` when the file changes. The HIGH rule is `fraud_score > 30`.
- New charges without a `fraud_features` row follow the status rule, then REVIEW. Never LOW.
- Tests run without a model API key and without `DATABASE_URL`.
