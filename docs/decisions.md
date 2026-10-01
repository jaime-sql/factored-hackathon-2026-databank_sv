# Decisions

- HIGH (`fraud_score > 30`) runs before the Pending and Reversed explanations, including when those charges have no feature row.
- A missing feature row on any other status is REVIEW, never LOW. Auto-close is not allowed without a model score.
- Audit history is append-only. Case and handoff rows may be updated. Nothing is deleted.
- Eval fields are ignored unless the runner presents `EVAL_RUNNER_TOKEN`. The metrics default hides that traffic and labels the include toggle as a fraud-enriched demo sample. `include_eval` and `include_test` are honored only for the admin token.
- `QA_TEST_TOKEN` marks a browser session as test traffic (`is_test`). Empty disables it. Eval runs never set the flag. Metrics and the audit export omit those rows unless an admin asks for them. The token value is not stored in the repo.
- The console does not compute label-based safe or unsafe rates. Those need `eval.case_labels`, which `app_rw` cannot read.
- `DATABASE_URL` stays in the environment and in Secret Manager. It is not committed.
