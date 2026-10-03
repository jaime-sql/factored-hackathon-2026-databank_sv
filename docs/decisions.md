# Decisions

## 1. Scope

**Decision.** The product handles transaction-level card-dispute intake for “no reconozco este cargo” about one selected charge. Duplicate charges appear only as a labeled synthetic fixture. Complaints data is used only for volume and SLA context.

**Why.** This keeps the customer journey narrow, auditable, and grounded in a specific transaction while preserving operational context.

**Alternatives considered.** General complaint handling, broad banking support, and treating duplicate charges as real production data.

**Evidence.** The repository describes a transaction-level dispute flow; the duplicate path is explicitly synthetic and labeled, and complaints are limited to volume and SLA context.

## 2. Routing order

**Decision.** Apply the rules in this order: (1) `fraud_score > 30` routes HIGH, offers a card block only after customer confirmation, then creates a human handoff packet; (2) Pending or Reversed charges receive a deterministic explanation; (3) all other cases go to LightGBM, which assigns REVIEW or LOW at `t_low = 0.000275603870032301`; (4) if the model fails, fall back to the rule and never auto-close.

**Why.** Deterministic safety and status explanations must precede learned routing, and model failure must not create an unsafe automatic resolution.

**Alternatives considered.** Running the model before deterministic rules, allowing an unconfirmed block, and allowing model failure to produce LOW.

**Evidence.** The README and routing design specify HIGH first, then Pending/Reversed explanations, then model bands; missing features route to REVIEW, never LOW.

## 3. Use a strict HIGH cut

**Decision.** HIGH is `fraud_score > 30`, not `fraud_score >= 30`.

**Why.** The strict cut avoids wrongful blocks at the boundary while retaining the observed HIGH fraud flags.

**Alternatives considered.** The inclusive `>= 30` cut.

**Evidence.** On test, all 334 HIGH flags were fraud, so wrongful blocks were 0 per 10k. The `>= 30` cut would have blocked 88 legitimate charges.

## 4. Keep the model despite a rule tie

**Decision.** Keep LightGBM for safe LOW auto-close routing, while treating the model and rule as tied on discrimination. Use validation for tuning; score the test set once, on Oct 3, with nothing tuned on it.

**Why.** The model's practical value is controlled automation, not a claimed PR-AUC win. Validation automation is 18.01% (`19,832` rule cases plus `99,708` LOW cases out of `663,624` charges), with 16.03% on test, while the fraud-miss target holds.

**Alternatives considered.** Replacing the model with the rule, or claiming the model materially beats the rule from the small PR-AUC difference.

**Evidence.** Test PR-AUC is 0.584 for the model, 0.583 for the rule, and 0.576 for logistic regression. The difference is +0.0007 with a 95% CI of −0.0007 to +0.0019; recall at 0.02% FPR is 58.2% for both. Validation missed fraud is 29/610 = 4.75% (CI 3.33–6.74%), and test missed fraud is 29/583 = 4.97% (CI 3.49–7.05%), so recall is 95.0% and the target holds.

## 5. Treat Mexico as a known fairness gap

**Decision.** Show Mexico's gap in the app as “Brecha conocida.” Do not tune per-country cuts in this build; treat them as future work.

**Why.** A single global `t_low` performs unevenly by country, and the cause is measurable: Mexico charges score lower overall, sending more Mexico fraud seen by the model to LOW.

**Alternatives considered.** Hiding the country result, tuning a Mexico-specific cut in this build, or presenting validation alone without the test note.

**Evidence.** Validation misses are Mexico 21/292 (7.2%), Colombia 4/181, and Argentina 4/137; Fisher p = 0.0074, about 0.02 after correcting for three comparisons. The global cut sends 15.7% (21/134) of Mexico fraud seen by the model to LOW, versus 5–6% elsewhere. On test, the gap narrows: 17/301 versus 8/116 and 4/157.

## 6. Use DuckDB locally and Databricks for masked layers

**Decision.** The reproducible pipeline is a one-command local run, `bash pipeline/run_all.sh`, using embedded DuckDB. It reads the read-only challenge S3 bucket and builds bronze, silver, and gold. Masked copies of all three layers are stored in Databricks Free Edition under `workspace.bronze`, `workspace.silver`, and `workspace.gold`. The app reads a masked slice from Supabase Postgres.

**Why.** DuckDB provides a local, reproducible engine; Databricks provides visible masked layers; Supabase provides the app's serving store without exposing unmasked data to the app.

**Alternatives considered.** Making Databricks the only pipeline runtime, uploading unmasked layers, or having the app read directly from the challenge bucket.

**Evidence.** Databricks counts match the local run: 4,425,008 transactions, 150,000 customers, and 400,000 products in each masked bronze and silver layer; gold contains 4,425,008 transactions, 150,000 customers, 4,291,915 fraud features, 4,291,915 fraud split rows, and 600 synthetic duplicates. Names, document numbers, contact details, addresses, birth dates, and coordinates are dropped; IDs are replaced with salted keys. Credit score, income, occupation, marital status, and education are kept for fairness analysis. The full field treatment is documented in `docs/data-quality.md` §8.

## 7. Keep the app stack narrow and auditable

**Decision.** Run FastAPI on GCP Cloud Run, use OpenAI for reply drafting, write every AI decision to an audit log, mask PII before any LLM call, and enforce prompt-injection guardrails.

**Why.** This separates deterministic case decisions from bounded reply drafting and preserves an explanation trail without sending raw PII to the model.

**Alternatives considered.** Letting the LLM choose routing, sending unmasked case data to the LLM, or omitting an audit trail.

**Evidence.** The app stack is FastAPI on Cloud Run with OpenAI reply drafting; the architecture states that the deterministic engine chooses the outcome and the model may only phrase text that the engine already decided.

## 8. Separate judge access and data

**Decision.** Share the judge token only in the submission email. Keep it separate from `EVAL_RUNNER_TOKEN`; the judge token receives a 403 on eval fields. Tag judge actions with `source='judge'` in `audit_live`; tag break-it rows `demo_attack` and exclude them from `audit_live`.

**Why.** Judge activity must be demonstrable without granting evaluation access or contaminating live operational metrics.

**Alternatives considered.** Reusing the evaluation token, exposing eval fields to the judge token, or mixing break-it traffic into live audit data.

**Evidence.** The access design specifies the separate tokens, the 403 behavior, `source='judge'`, `demo_attack`, and exclusion of break-it rows from `audit_live`.

## 9. Keep commit authorship clean

**Decision.** Do not use co-authored commits; only `jaime-sql` appears as author.

**Why.** The repository's authorship must clearly reflect Jaime's project ownership and remain transparent to judges.

**Alternatives considered.** Adding tool, agent, or other co-authors to commits.

**Evidence.** Repository history shows only `jaime-sql` as author.

## 10. Generate the reply draft in the background

**Decision.** The handoff reply draft (gpt-4o-mini, one call per handoff) runs in the background, off the customer's request path. The console shows "Borrador en preparación…" until it is ready.

**Why.** The customer's answer and the card block must not wait on the LLM. The draft is only for the human agent.

**Alternatives considered.** Generating the draft inline before replying to the customer.

**Evidence.** On preview `3ade50a`, REVIEW intake went from 3.2 s to 1.28 s and block-confirm went from 3.75 s to 2.51 s.
